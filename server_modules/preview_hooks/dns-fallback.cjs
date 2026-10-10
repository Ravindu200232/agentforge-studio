// Loaded into every Node process the Studio starts for a project (NODE_OPTIONS --require, set by node_hooks.py): the agent's
// commands (the seed, the tests, `next build`), the end-to-end runs and the preview.
//
// A home router often answers a name wrongly once and rightly the next time, and some never answer an SRV question at all.
// The Studio's own connection check already asks again and then asks public DNS (scripts/mongo-ping.mjs), but the app, its
// seed and its tests used this computer's DNS alone, so a check could pass while the seed failed with `querySrv EREFUSED`
// or `getaddrinfo ENOTFOUND <cluster>-shard-00-01...` and every journey after it. This does the same as the check for them:
// a name this computer could not look up is asked once more, then of public DNS. Nothing changes for a name that resolves,
// for an address, or for a local name. AGENTFORGE_DNS_FALLBACK=0 turns it off; AGENTFORGE_PUBLIC_DNS replaces the servers.
'use strict'
const dns = require('node:dns')
const net = require('node:net')
const util = require('node:util')

if (process.env.AGENTFORGE_DNS_FALLBACK !== '0' && !dns.__agentforgeFallback) {
  const PUBLIC = String(process.env.AGENTFORGE_PUBLIC_DNS || '1.1.1.1,8.8.8.8').split(',').map((s) => s.trim()).filter(Boolean)
  const FLAKY = new Set(['ENOTFOUND', 'EAI_AGAIN', 'EAI_FAIL', 'ENODATA', 'ESERVFAIL', 'ETIMEOUT', 'ECONNREFUSED', 'EREFUSED'])
  const LOCAL = /(^localhost$)|(\.(localhost|local|internal|lan|home)$)/i
  const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

  let resolver = null
  const publicResolver = () => {
    if (!resolver) {
      resolver = new dns.promises.Resolver({ timeout: 4000, tries: 2 })
      resolver.setServers(PUBLIC)
    }
    return resolver
  }

  /** Whether a failed lookup of `host` is worth asking again and then of public DNS. */
  const worthAsking = (host, error) => Boolean(error && FLAKY.has(error.code) && typeof host === 'string'
    && host.includes('.') && !net.isIP(host) && !LOCAL.test(host))

  const optionsOf = (options) => (typeof options === 'number' ? { family: options } : (options || {}))

  async function fromPublic(host, options) {
    const family = Number(options.family) || 0
    const rows = []
    if (family !== 6) {
      try { rows.push(...(await publicResolver().resolve4(host)).map((address) => ({ address, family: 4 }))) } catch { /* none */ }
    }
    if (family === 6 || (family === 0 && !rows.length)) {
      try { rows.push(...(await publicResolver().resolve6(host)).map((address) => ({ address, family: 6 }))) } catch { /* none */ }
    }
    return rows
  }

  // dns.lookup: what net.connect, tls.connect, fetch and every database driver use to find an address.
  const systemLookup = dns.lookup
  function lookup(hostname, options, callback) {
    if (typeof options === 'function') { callback = options; options = {} }
    const wanted = optionsOf(options)
    systemLookup.call(dns, hostname, wanted, (error, address, family) => {
      if (!worthAsking(hostname, error)) { callback(error, address, family); return }
      setTimeout(() => systemLookup.call(dns, hostname, wanted, (again, address2, family2) => {
        if (!worthAsking(hostname, again)) { callback(again, address2, family2); return }
        fromPublic(hostname, wanted).then((rows) => {
          if (!rows.length) callback(error)
          else if (wanted.all) callback(null, rows)
          else callback(null, rows[0].address, rows[0].family)
        }, () => callback(error))
      }), 300)
    })
  }
  lookup[util.promisify.custom] = (hostname, options) => new Promise((resolve, reject) => {
    lookup(hostname, options || {}, (error, address, family) => {
      if (error) reject(error)
      else resolve(optionsOf(options).all ? address : { address, family })
    })
  })
  dns.lookup = lookup

  const promisesLookup = dns.promises.lookup
  dns.promises.lookup = async function (hostname, options) {
    try {
      return await promisesLookup.call(dns.promises, hostname, options)
    } catch (error) {
      if (!worthAsking(hostname, error)) throw error
      await pause(300)
      try { return await promisesLookup.call(dns.promises, hostname, options) } catch (again) { if (!worthAsking(hostname, again)) throw again }
      const wanted = optionsOf(options)
      const rows = await fromPublic(hostname, wanted)
      if (!rows.length) throw error
      return wanted.all ? rows : rows[0]
    }
  }

  // The SRV and TXT records a mongodb+srv:// string is looked up by (the MongoDB driver asks these first).
  for (const name of ['resolveSrv', 'resolveTxt']) {
    const own = dns.promises[name]
    const asked = async function (hostname) {
      try {
        return await own.call(dns.promises, hostname)
      } catch (error) {
        if (!worthAsking(hostname, error)) throw error
        await pause(300)
        try { return await own.call(dns.promises, hostname) } catch (again) { if (!worthAsking(hostname, again)) throw again }
        try { return await publicResolver()[name](hostname) } catch { throw error }
      }
    }
    dns.promises[name] = asked
    dns[name] = function (hostname, callback) {
      asked(hostname).then((rows) => callback(null, rows), (error) => callback(error))
    }
  }

  dns.__agentforgeFallback = true
  // `import { lookup } from 'node:dns'` in an ES module sees the new functions too.
  try { require('node:module').syncBuiltinESMExports() } catch { /* an older Node: CommonJS and default imports still do */ }
}
