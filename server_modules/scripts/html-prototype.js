(() => {
  const { routes, accounts: records, signInRoute, signUp } = window.__afPreview
  delete window.__afPreview
  const accounts = records.map(account => ({ ...account, name: account.display_name || account.role }))
  const mount = document.getElementById('af-page')
  const roleFor = value => accounts.find(a => [a.email, a.role_key, a.role].includes(value)) || null
  let user = roleFor(new URLSearchParams(location.search).get('as'))
  let params = {}

  function match(path) {
    const parts = path.split('/').filter(Boolean)
    const exact = routes.find(row => row.route === path)
    if (exact) return [exact, {}]
    for (const row of routes) {
      const given = row.route.split('/').filter(Boolean)
      if (given.length !== parts.length) continue
      const values = {}
      const fits = given.every((part, i) => {
        if (part.startsWith(':') || /^\[.+\]$/.test(part)) {
          values[part.replace(/^\[|\]$|^:/g, '')] = parts[i]
          return true
        }
        return part === parts[i]
      })
      if (fits) return [row, values]
    }
    return []
  }

  function navigate(path) {
    if (location.hash === '#' + path) render()
    else location.hash = path
  }

  function setUser(account) {
    user = account
    window.__afUser = user?.email || ''
  }

  function enter(account) {
    if (!account) return null
    setUser(account)
    navigate(user.lands_on || '/')
    return user
  }

  function canOpen(row) {
    if (!row.signed_in || row.route === signInRoute) return true
    if (!user) return false
    if (!row.roles?.length) return true
    const role = value => String(value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-')
    return user.can_open?.some(page => page.route === row.route)
      || row.roles.some(name => [user.role, user.role_key].map(role).includes(role(name)))
  }

  function render() {
    const requested = location.hash.slice(1).split('?')[0] || '/'
    let [row, values] = match(requested)
    if (!row) [row, values] = match(signInRoute || '/')
    row ||= routes[0]
    if (!row) return
    if (!canOpen(row)) {
      const [landing] = user?.lands_on ? match(user.lands_on) : []
      const target = landing && canOpen(landing) ? user.lands_on : signInRoute
      if (target && target !== requested) {
        navigate(target)
      } else {
        mount.textContent = 'This page requires a permitted demo account.'
      }
      return
    }
    params = values || {}
    mount.dataset.afRoute = row.route
    if (row.pending) {
      mount.textContent = 'This screen is being prepared.'
      return
    }
    mount.innerHTML = row.markup
    for (const link of document.querySelectorAll('a[href^="#/"]')) {
      if (link.getAttribute('href') === '#' + requested) link.setAttribute('aria-current', 'page')
      else link.removeAttribute('aria-current')
    }
    window.scrollTo(0, 0)
    window.dispatchEvent(new CustomEvent('agentforge:route', { detail: { route: row.route, params, user } }))
  }

  window.AgentForgePreview = {
    navigate,
    get user() { return user },
    get params() { return params },
    signIn: (email, password) => enter(accounts.find(a => a.email.toLowerCase() === email.trim().toLowerCase() && a.password === password)),
    signUp: (name, email) => {
      const account = roleFor(signUp?.role_key)
      return account ? enter({ ...account, name, email }) : null
    },
    signOut() { setUser(null); navigate(signInRoute || '/') },
  }
  setUser(user)
  window.addEventListener('hashchange', render)
  window.addEventListener('DOMContentLoaded', render)
})()
