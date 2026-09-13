function parseJson(raw) {
  try {
    return JSON.parse(String(raw || "{}"))
  } catch (e) {
    return null
  }
}

function parseStatus(raw) {
  var data = parseJson(raw)
  if (!data || typeof data !== "object")
    return { ok: false, error: "Failed to parse Proton VPN status" }
  if (data.ok === false)
    return { ok: false, error: String(data.error || "Proton VPN status failed") }
  return {
    ok: true,
    loggedIn: data.loggedIn === true,
    connected: data.connected === true,
    country: String(data.country || "").toUpperCase(),
    countryName: String(data.countryName || ""),
    city: String(data.city || ""),
    server: String(data.server || ""),
    load: data.load,
    error: String(data.error || "")
  }
}

function parseCountries(raw) {
  var data = parseJson(raw)
  if (!data || typeof data !== "object")
    return { ok: false, error: "Failed to parse country list", countries: [] }
  if (data.ok === false)
    return { ok: false, error: String(data.error || "Country list failed"), countries: [] }
  var list = data.countries
  if (!Array.isArray(list)) list = []
  return { ok: true, error: "", countries: list }
}

function flagEmoji(code) {
  var value = String(code || "").toUpperCase()
  if (!/^[A-Z]{2}$/.test(value)) return ""
  return String.fromCodePoint(0x1F1E6 + value.charCodeAt(0) - 65, 0x1F1E6 + value.charCodeAt(1) - 65)
}

function countryMatches(country, query) {
  var q = String(query || "").trim().toLowerCase()
  if (q === "") return true
  if (!country) return false
  var code = String(country.code || "").toLowerCase()
  var name = String(country.name || "").toLowerCase()
  if (code.indexOf(q) !== -1 || name.indexOf(q) !== -1) return true
  var cities = country.cities
  if (!Array.isArray(cities)) return false
  for (var i = 0; i < cities.length; i++) {
    if (String((cities[i] && cities[i].name) || "").toLowerCase().indexOf(q) !== -1) return true
  }
  return false
}

function filterCountries(countries, query) {
  var list = Array.isArray(countries) ? countries : []
  var q = String(query || "").trim()
  if (q === "") return list
  var result = []
  for (var i = 0; i < list.length; i++) {
    if (countryMatches(list[i], q)) result.push(list[i])
  }
  return result
}

function filterCities(cities, query) {
  var list = Array.isArray(cities) ? cities : []
  var q = String(query || "").trim().toLowerCase()
  if (q === "") return list
  var result = []
  for (var i = 0; i < list.length; i++) {
    var name = String((list[i] && list[i].name) || "").toLowerCase()
    if (name.indexOf(q) !== -1) result.push(list[i])
  }
  return result
}

function findCountry(countries, code) {
  var needle = String(code || "").toUpperCase()
  var list = Array.isArray(countries) ? countries : []
  for (var i = 0; i < list.length; i++) {
    if (String(list[i].code || "").toUpperCase() === needle) return list[i]
  }
  return null
}

function nextRecents(current, code) {
  var name = String(code || "").toUpperCase()
  if (!/^[A-Z]{2}$/.test(name)) return Array.isArray(current) ? current.slice(0, 5) : []
  var next = [name]
  var list = Array.isArray(current) ? current : []
  for (var i = 0; i < list.length && next.length < 5; i++) {
    var existing = String(list[i] || "").toUpperCase()
    if (/^[A-Z]{2}$/.test(existing) && existing !== name) next.push(existing)
  }
  return next
}

function fileUrlToPath(url) {
  var value = String(url || "")
  if (value.indexOf("file://") === 0) value = value.substring(7)
  if (value.indexOf("localhost/") === 0) value = value.substring(9)
  try {
    return decodeURIComponent(value)
  } catch (e) {
    return value
  }
}

function loadLabel(load) {
  var n = parseInt(String(load), 10)
  if (!isFinite(n)) return ""
  return n + "%"
}
