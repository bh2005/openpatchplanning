import axios from 'axios'

const TOKEN_KEY = 'opp_auth_token'
const USER_KEY  = 'opp_user'

export function getToken()   { return localStorage.getItem(TOKEN_KEY) || '' }
export function setToken(t)  { localStorage.setItem(TOKEN_KEY, t) }
export function setUser(u)   { localStorage.setItem(USER_KEY, JSON.stringify(u || {})) }
export function getUser()    { try { return JSON.parse(localStorage.getItem(USER_KEY) || '{}') } catch { return {} } }
export function clearToken() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY) }
export function isLoggedIn() { return !!getToken() }
export function isAdmin()    { return (getUser().roles || []).includes('admin') }
export function hasRole(...roles) { const r = getUser().roles || []; return r.includes('admin') || roles.some(x => r.includes(x)) }

const http = axios.create({ baseURL: '' })

http.interceptors.request.use(cfg => {
  const t = getToken()
  if (t) cfg.headers['X-Auth-Token'] = t
  return cfg
})

http.interceptors.response.use(r => r, err => {
  const url = err.config?.url || ''
  if (err.response?.status === 401 && getToken() && !url.includes('/auth/login') && !url.includes('/auth/change-password')) {
    clearToken()
    if (location.pathname !== '/login') location.href = '/login'
  }
  return Promise.reject(err)
})

/** Lesbare Fehlermeldung aus einer API-Antwort (FastAPI: detail als Text oder als Liste von Validierungsfehlern). */
export function errText(e, fallback = 'Fehler') {
  const d = e?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map(x => `${(x.loc || []).slice(1).join('.')}: ${x.msg}`).join('; ')
  return fallback
}

const get  = (url, params) => http.get(url, { params }).then(r => r.data)
const post = (url, body, cfg) => http.post(url, body, cfg).then(r => r.data)
const put  = (url, body) => http.put(url, body).then(r => r.data)
const del  = url => http.delete(url).then(r => r.data)

export const api = {
  // Anmeldung
  login:          (username, password) => post('/auth/login', { username, password }),
  logout:         () => post('/auth/logout'),
  me:             () => get('/auth/me'),
  changePassword: (current_password, new_password) => post('/auth/change-password', { current_password, new_password }),

  // Übersicht
  stats: () => get('/api/stats'),

  // Standorte und Locations
  sites:          () => get('/api/sites'),
  createSite:     b => post('/api/sites', b),
  updateSite:     (id, b) => put(`/api/sites/${id}`, b),
  deleteSite:     id => del(`/api/sites/${id}`),
  locations:      site_id => get('/api/locations', site_id ? { site_id } : {}),
  createLocation: b => post('/api/locations', b),
  updateLocation: (id, b) => put(`/api/locations/${id}`, b),
  deleteLocation: id => del(`/api/locations/${id}`),

  // Geräte und Ports
  devices:      params => get('/api/devices', params),
  device:       id => get(`/api/devices/${id}`),
  createDevice: b => post('/api/devices', b),
  updateDevice: (id, b) => put(`/api/devices/${id}`, b),
  deleteDevice: id => del(`/api/devices/${id}`),
  createPort:   (did, b) => post(`/api/devices/${did}/ports`, b),
  bulkPorts:    (did, b) => post(`/api/devices/${did}/ports/bulk`, b),
  updatePort:   (id, b) => put(`/api/ports/${id}`, b),
  deletePort:   id => del(`/api/ports/${id}`),
  setPeer:      (id, peer_port_id) => put(`/api/ports/${id}/peer`, { peer_port_id }),
  setCable:     (id, body) => put(`/api/ports/${id}/cable`, body),
  cables:       params => get('/api/cables', params),
  updateCable:  (id, body) => put(`/api/cables/${id}`, body),

  // Patchaufträge
  workorders:        params => get('/api/workorders', params),
  workorder:         id => get(`/api/workorders/${id}`),
  createWorkorder:   b => post('/api/workorders', b),
  updateWorkorder:   (id, b) => put(`/api/workorders/${id}`, b),
  deleteWorkorder:   id => del(`/api/workorders/${id}`),
  workorderTransition: (id, action) => post(`/api/workorders/${id}/transition/${action}`),
  workorderItems:    id => get(`/api/workorders/${id}/items`),
  addWorkitem:       (wid, b) => post(`/api/workorders/${wid}/items`, b),
  updateWorkitem:    (wid, iid, b) => put(`/api/workorders/${wid}/items/${iid}`, b),
  deleteWorkitem:    (wid, iid) => del(`/api/workorders/${wid}/items/${iid}`),
  executeWorkitem:   (wid, iid, b) => post(`/api/workorders/${wid}/items/${iid}/execute`, b),
  reopenWorkitem:    (wid, iid) => post(`/api/workorders/${wid}/items/${iid}/reopen`),

  // Import
  importFields:   () => get('/api/import/fields'),
  csvPreview:     (file, kind) => { const f = new FormData(); f.append('file', file); f.append('kind', kind); return post('/api/import/csv/preview', f) },
  csvImport:      (file, kind, mapping, opts) => {
    const f = new FormData()
    f.append('file', file); f.append('kind', kind); f.append('mapping', JSON.stringify(mapping || {}))
    f.append('dry_run', String(opts.dry_run)); f.append('atomic', String(opts.atomic)); f.append('create_locations', String(opts.create_locations))
    return post('/api/import/csv', f)
  },
  jsonImport:     b => post('/api/import/json', b),
  importRuns:     () => get('/api/import/runs'),

  // Verwaltung
  users:          () => get('/api/users'),
  createUser:     b => post('/api/users', b),
  updateUser:     (id, b) => put(`/api/users/${id}`, b),
  deleteUser:     id => del(`/api/users/${id}`),
  resetPassword:  (id, new_password) => post(`/api/users/${id}/reset-password`, { new_password }),
  revokeSessions: id => post(`/api/users/${id}/revoke-sessions`),
  tokens:         () => get('/api/tokens'),
  createToken:    b => post('/api/tokens', b),
  revokeToken:    id => del(`/api/tokens/${id}`),
  audit:          params => get('/api/audit', params),
}
