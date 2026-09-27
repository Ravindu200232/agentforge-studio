/* Prototype runtime: routes, links, the demo session, access and sign-in.
 * Written by the engine and identical for every prototype, so the flow between pages never depends on what a model drew.
 * It reads window.PROTOTYPE (assets/flow.js: routes, accounts, signIn) and is loaded after it. Pages mark up what they need:
 *   [data-go="/route"]                 a link to that page (the href is filled in)
 *   [data-roles="a b"]                 shown only to those signed-in roles
 *   [data-user="name|email|role|initials"]  filled from the signed-in account
 *   form[data-signin]                  the sign-in form (an email and a password input); [data-signin-error] receives the message
 *   [data-demo-fill="email"]           fills the sign-in form with that demo account
 *   [data-demo-signin="email|role"]    signs in as that demo account at once
 *   [data-signout]                     signs out
 */
(function () {
  "use strict";
  var P = window.PROTOTYPE = window.PROTOTYPE || {};
  var KEY = "prototype.session";
  var routes = P.routes || [];
  var accounts = P.accounts || [];
  var signInRoute = (P.signIn && P.signIn.route) || "";
  var signInFile = (P.signIn && P.signIn.file) || "";
  var stage = { list: P.routes || [] };

  function norm(value) { return String(value == null ? "" : value).trim().toLowerCase(); }
  function read() { try { var raw = sessionStorage.getItem(KEY); return raw ? JSON.parse(raw) : null; } catch (e) { return null; } }
  function write(value) {
    try { if (value) sessionStorage.setItem(KEY, JSON.stringify(value)); else sessionStorage.removeItem(KEY); } catch (e) { /* storage may be blocked */ }
  }
  function byRoute(route) {
    var wanted = (String(route || "").replace(/\/+$/, "")) || "/";
    for (var i = 0; i < routes.length; i++) if (((routes[i].route || "").replace(/\/+$/, "") || "/") === wanted) return routes[i];
    return null;
  }
  function currentFile() { return decodeURIComponent(location.pathname.split("/").pop() || "") || (routes[0] && routes[0].file) || ""; }
  function currentRoute() {
    var file = currentFile();
    for (var i = 0; i < routes.length; i++) if (routes[i].file === file) return routes[i];
    return null;
  }
  function go(route) { var target = byRoute(route); if (target) location.href = target.file; }

  P.user = function () { return read(); };
  P.go = go;

  /* a route with no roles is open to everyone; the sign-in page always is */
  P.can = function (route) {
    var target = typeof route === "string" ? byRoute(route) : route;
    if (!target || !target.roles || !target.roles.length || target.route === signInRoute) return true;
    var user = read();
    if (!user) return false;
    for (var i = 0; i < target.roles.length; i++) if (norm(target.roles[i]) === norm(user.role)) return true;
    return false;
  };

  P.signIn = function (emailOrRole, password) {
    var key = norm(emailOrRole), account = null;
    for (var i = 0; i < accounts.length && !account; i++) {
      var a = accounts[i];
      if (norm(a.email) === key || norm(a.roleKey) === key || norm(a.role) === key) account = a;
    }
    if (!account) return { ok: false, error: "We could not find an account for that email." };
    if (password != null && password !== "" && password !== account.password) return { ok: false, error: "That password does not match this account." };
    write({ email: account.email, name: account.name, role: account.roleKey, roleName: account.role, landsOn: account.landsOn });
    go(account.landsOn);
    return { ok: true, account: account, route: account.landsOn };
  };

  P.signOut = function () { write(null); if (signInRoute) go(signInRoute); else location.reload(); };

  /* ---- what the page shows for the signed-in role ---- */
  function applyLinks() {
    var file = currentFile();
    Array.prototype.forEach.call(document.querySelectorAll("[data-go]"), function (el) {
      var target = byRoute(el.getAttribute("data-go"));
      if (!target) { el.setAttribute("data-dead-link", ""); return; }
      if (el.tagName === "A") el.setAttribute("href", target.file);
      else if (!el.__goBound) { el.__goBound = true; el.addEventListener("click", function () { location.href = target.file; }); }
      if (target.file === file) { el.setAttribute("aria-current", "page"); el.classList.add("is-active"); }
    });
  }

  function applyUser() {
    var user = read();
    Array.prototype.forEach.call(document.querySelectorAll("[data-user]"), function (el) {
      var field = el.getAttribute("data-user");
      var text = "";
      if (user) {
        if (field === "initials") text = String(user.name || "").split(/\s+/).map(function (w) { return w.charAt(0); }).join("").slice(0, 2).toUpperCase();
        else if (field === "role") text = user.roleName || user.role || "";
        else text = user[field] || "";
      }
      el.textContent = text;
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-roles]"), function (el) {
      var allowed = (el.getAttribute("data-roles") || "").split(/\s+/).filter(Boolean).map(norm);
      var show = !!user && allowed.indexOf(norm(user.role)) !== -1;
      if (show) el.removeAttribute("hidden"); else el.setAttribute("hidden", "");
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-signed-out]"), function (el) {
      if (user) el.setAttribute("hidden", ""); else el.removeAttribute("hidden");
    });
  }

  /* ---- who may open this page ---- */
  function guard() {
    var here = currentRoute();
    if (!here || P.can(here)) return;
    var main = document.querySelector("[data-page-content]") || document.querySelector("main");
    if (!main) return;
    Array.prototype.forEach.call(main.children, function (child) { child.setAttribute("hidden", ""); });
    var user = read();
    var box = document.createElement("div");
    box.className = "access-notice is-visible";
    box.setAttribute("role", "alert");
    var title = document.createElement("h2"), text = document.createElement("p"), link = document.createElement("a");
    if (!user) {
      title.textContent = "Sign in to continue";
      text.textContent = "This page is for signed-in accounts.";
      link.textContent = "Go to sign in"; link.setAttribute("data-go", signInRoute);
    } else {
      title.textContent = "This page is not available to your account";
      text.textContent = "You are signed in as " + (user.roleName || user.role) + ", which cannot open " + here.name + ".";
      link.textContent = "Go to your page"; link.setAttribute("data-go", user.landsOn || signInRoute);
    }
    link.className = "btn btn-primary";
    box.appendChild(title); box.appendChild(text); box.appendChild(link);
    main.appendChild(box);
    applyLinks();
  }

  /* ---- sign-in form and demo accounts ---- */
  function message(form, text) {
    var target = (form && form.querySelector("[data-signin-error]")) || document.querySelector("[data-signin-error]");
    if (!target) return;
    target.textContent = text || "";
    if (text) target.removeAttribute("hidden"); else target.setAttribute("hidden", "");
  }

  function bindSignIn() {
    Array.prototype.forEach.call(document.querySelectorAll("form[data-signin]"), function (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        var email = form.querySelector("input[type=email], input[name=email]");
        var password = form.querySelector("input[type=password]");
        if (!email || !norm(email.value)) { message(form, "Enter your email address."); if (email) email.focus(); return; }
        if (!password || !password.value) { message(form, "Enter your password."); if (password) password.focus(); return; }
        var result = P.signIn(email.value, password.value);
        if (!result.ok) message(form, result.error);
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-demo-fill]"), function (el) {
      el.addEventListener("click", function (event) {
        event.preventDefault();
        var key = norm(el.getAttribute("data-demo-fill")), account = null;
        for (var i = 0; i < accounts.length; i++) if (norm(accounts[i].email) === key || norm(accounts[i].roleKey) === key) account = accounts[i];
        var form = document.querySelector("form[data-signin]");
        if (!account || !form) return;
        var email = form.querySelector("input[type=email], input[name=email]"), password = form.querySelector("input[type=password]");
        if (email) email.value = account.email;
        if (password) password.value = account.password;
        message(form, "");
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-demo-signin]"), function (el) {
      el.addEventListener("click", function (event) { event.preventDefault(); P.signIn(el.getAttribute("data-demo-signin")); });
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-signout]"), function (el) {
      el.addEventListener("click", function (event) { event.preventDefault(); P.signOut(); });
    });
  }

  function start() { applyLinks(); applyUser(); guard(); bindSignIn(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
