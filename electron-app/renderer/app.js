// ── Backend API base ──────────────────────────────────────────────────────────
const API = 'http://127.0.0.1:7654'

async function api(path, opts) {
  try {
    const r = await fetch(API + path, opts)
    return await r.json()
  } catch (e) {
    console.error('API error', path, e)
    return null
  }
}

// ── Navigation ────────────────────────────────────────────────────────────────
document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const idx = +btn.dataset.page
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'))
    btn.classList.add('active')
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'))
    document.getElementById('page-' + idx).classList.add('active')
  })
})

// ── Window controls ───────────────────────────────────────────────────────────
document.getElementById('btn-min').addEventListener('click', () => window.electronAPI.minimize())
document.getElementById('btn-max').addEventListener('click', () => window.electronAPI.maximize())
document.getElementById('btn-close').addEventListener('click', () => window.electronAPI.close())

const appEl = document.getElementById('app')
window.electronAPI.isMaximized().then(v => appEl.classList.toggle('maximized', v))
window.electronAPI.onMaximizeChange(v => appEl.classList.toggle('maximized', v))

// ── Slider ↔ value-box sync ───────────────────────────────────────────────────
function formatSlider(val, mode) {
  if (mode === 'pct')  return val + '%'
  if (mode === 'dec2') return (val / 100).toFixed(2)
  return String(val)
}

function parseSliderBox(text, mode) {
  const m = text.replace(',', '.').match(/-?\d+(?:\.\d+)?/)
  if (!m) return null
  const n = parseFloat(m[0])
  if (mode === 'dec2') return Math.round(n * 100)
  return Math.round(n)
}

document.querySelectorAll('.slider-input').forEach(slider => {
  const valId = slider.id.replace(/^s(\d*)-/, (_, n) => n ? `sv${n}-` : 'sv-')
    .replace('s-', 'sv-').replace('s2-', 'sv2-').replace('s3-', 'sv3-')
  // build correct box id by replacing slider id prefix
  const boxId = slider.id.replace(/^(s\d*-)/, m => m.replace('s', 'sv'))
  const box = document.getElementById(boxId)
  if (!box) return

  const mode = slider.dataset.mode || 'int'

  // Live slider update
  slider.addEventListener('input', () => {
    box.value = formatSlider(+slider.value, mode)
    updateSliderTrack(slider)
  })

  // Box → slider
  box.addEventListener('change', () => {
    const v = parseSliderBox(box.value, mode)
    if (v == null) { box.value = formatSlider(+slider.value, mode); return }
    const clamped = Math.max(+slider.min, Math.min(+slider.max, v))
    slider.value = clamped
    box.value = formatSlider(clamped, mode)
    updateSliderTrack(slider)
  })

  box.addEventListener('keydown', e => { if (e.key === 'Enter') box.blur() })

  // Initial fill
  updateSliderTrack(slider)
})

function updateSliderTrack(slider) {
  const min = +slider.min, max = +slider.max, val = +slider.value
  const pct = ((val - min) / (max - min)) * 100
  slider.style.background =
    `linear-gradient(to right, var(--green) ${pct}%, var(--border) ${pct}%)`
}

// Init all tracks on load
document.querySelectorAll('.slider-input').forEach(updateSliderTrack)

// ── Game status polling ───────────────────────────────────────────────────────
async function pollStatus() {
  const data = await api('/api/status')
  if (!data) return

  const dot = document.getElementById('status-dot')
  const gl  = document.getElementById('status-gl')
  const rv  = document.getElementById('status-rv')
  const cfg = document.getElementById('sc-cfg')

  if (data.game_running) {
    dot.style.color = 'var(--green)'
    gl.textContent = 'Game detected'
    gl.style.color = 'var(--green)'
    rv.textContent = 'Running'
    rv.style.color = 'var(--green)'
  } else {
    dot.style.color = 'var(--red)'
    gl.textContent = 'Game not detected'
    gl.style.color = 'var(--text-dim)'
    rv.textContent = 'Not Running'
    rv.style.color = 'var(--red)'
  }

  if (cfg) {
    cfg.textContent = data.config_found ? 'Detected' : 'Not Found'
    cfg.style.color = data.config_found ? 'var(--green)' : 'var(--red)'
  }
}

pollStatus()
setInterval(pollStatus, 3000)

// ── Profile system ────────────────────────────────────────────────────────────
async function loadProfiles() {
  const data = await api('/api/profiles')
  if (!data) return
  const sel = document.getElementById('profile-select')
  const current = sel.value
  sel.innerHTML = '<option>Default Profile</option>'
  for (const name of data.profiles) {
    const opt = document.createElement('option')
    opt.textContent = name
    sel.appendChild(opt)
  }
  if ([...sel.options].some(o => o.value === current)) sel.value = current
}

function collectSettings() {
  const s = {}
  document.querySelectorAll('.slider-input[id^="s-"], .slider-input[id^="s2-"]').forEach(el => {
    s[el.id] = +el.value
  })
  document.querySelectorAll('input[type=checkbox]').forEach(el => {
    s[el.id] = el.checked
  })
  document.querySelectorAll('select:not(#profile-select)').forEach(el => {
    s[el.id] = el.selectedIndex
  })
  return s
}

function applySettings(settings) {
  for (const [key, val] of Object.entries(settings)) {
    const el = document.getElementById(key)
    if (!el) continue
    if (el.type === 'range') {
      el.value = val
      const boxId = el.id.replace(/^(s\d*-)/, m => m.replace('s', 'sv'))
      const box = document.getElementById(boxId)
      if (box) box.value = formatSlider(+val, el.dataset.mode || 'int')
      updateSliderTrack(el)
    } else if (el.type === 'checkbox') {
      el.checked = !!val
    } else if (el.tagName === 'SELECT') {
      el.selectedIndex = +val
    }
  }
}

// Profile dialog
const profileDialog = document.getElementById('profile-dialog')

document.getElementById('btn-profile-add').addEventListener('click', () => {
  profileDialog.style.display = 'flex'
  document.getElementById('dlg-name').value = ''
  document.getElementById('dlg-error').textContent = ''
  document.getElementById('dlg-name').focus()
})

document.getElementById('dlg-close').addEventListener('click', () => {
  profileDialog.style.display = 'none'
})
document.getElementById('dlg-cancel').addEventListener('click', () => {
  profileDialog.style.display = 'none'
})
document.getElementById('dlg-save').addEventListener('click', async () => {
  const name = document.getElementById('dlg-name').value.trim()
  const errEl = document.getElementById('dlg-error')
  if (!name) { errEl.textContent = 'Введите название профиля'; return }
  if (name.toLowerCase() === 'default profile') { errEl.textContent = 'Название зарезервировано'; return }
  const res = await api('/api/profiles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, settings: collectSettings() }),
  })
  if (res && res.ok) {
    profileDialog.style.display = 'none'
    await loadProfiles()
    document.getElementById('profile-select').value = name
    document.getElementById('sc-profile').textContent = name
  } else {
    errEl.textContent = res?.error || 'Ошибка сохранения'
  }
})
document.getElementById('dlg-name').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('dlg-save').click()
})

document.getElementById('btn-profile-del').addEventListener('click', async () => {
  const name = document.getElementById('profile-select').value
  if (name === 'Default Profile') return
  await api(`/api/profiles/${encodeURIComponent(name)}`, { method: 'DELETE' })
  await loadProfiles()
})

document.getElementById('profile-select').addEventListener('change', async () => {
  const name = document.getElementById('profile-select').value
  document.getElementById('sc-profile').textContent = name
  if (name === 'Default Profile') return
  const res = await api(`/api/profiles/${encodeURIComponent(name)}`)
  if (res && res.ok && res.settings) applySettings(res.settings)
})

loadProfiles()

// ── Apply changes ─────────────────────────────────────────────────────────────
document.getElementById('btn-apply').addEventListener('click', () => {
  const now = new Date()
  const lbl = `Today, ${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}`
  const el = document.getElementById('sc-lastupdated')
  if (el) { el.textContent = lbl; el.style.color = 'var(--green)' }
})

// ── Update system ─────────────────────────────────────────────────────────────
;(function () {
  let state = 'idle'   // 'idle' | 'checking' | 'downloading' | 'ready' | 'installing'
  let installerPath = null
  let pendingVersion = ''

  const btnUpd      = document.getElementById('btn-check-update')
  const progressWrap = document.getElementById('upd-progress-wrap')
  const progressFill = document.getElementById('upd-progress-fill')
  const progressLbl  = document.getElementById('upd-progress-lbl')
  const infoStatus   = document.getElementById('info-status')

  function setProgress(pct) {
    progressFill.style.width = pct + '%'
    if (progressLbl) progressLbl.textContent = pct + '%'
  }

  // Live download progress from main process
  window.electronAPI.onUpdateProgress(pct => {
    if (state !== 'downloading') return
    setProgress(pct)
    btnUpd.textContent = `⬇  Загрузка v${pendingVersion}… ${pct}%`
  })

  btnUpd.addEventListener('click', async () => {
    if (state === 'ready') {
      state = 'installing'
      btnUpd.textContent = '⏳  Устанавливаем...'
      btnUpd.disabled = true
      await window.electronAPI.installUpdate(installerPath)
      return
    }
    if (state !== 'idle') return

    // ── Step 1: check ──────────────────────────────────────────────────────
    state = 'checking'
    btnUpd.textContent = '⏳  Проверка...'
    btnUpd.classList.remove('upd-btn-ready', 'upd-btn-install', 'upd-btn-downloading')
    btnUpd.disabled = true
    progressWrap.style.display = 'none'

    const data = await api('/api/update/check')
    if (!data || !data.ok) {
      state = 'idle'
      btnUpd.textContent = '⚠  Ошибка проверки — повторить'
      btnUpd.disabled = false
      setTimeout(() => { if (state === 'idle') btnUpd.textContent = '↓  Проверить обновления' }, 4000)
      return
    }

    const vTuple = v => v.split('.').map(Number)
    const newer = JSON.stringify(vTuple(data.version)) > JSON.stringify(vTuple(data.current))

    if (!newer) {
      state = 'idle'
      btnUpd.textContent = '✓  Актуальная версия'
      btnUpd.disabled = false
      if (infoStatus) infoStatus.textContent = 'Up to date'
      setTimeout(() => { if (state === 'idle') btnUpd.textContent = '↓  Проверить обновления' }, 3000)
      return
    }

    if (!data.download_url) {
      // No installer asset on GitHub release — just open releases page
      state = 'idle'
      btnUpd.textContent = `⬡  v${data.version} — открыть страницу`
      btnUpd.classList.add('upd-btn-ready')
      btnUpd.disabled = false
      btnUpd.addEventListener('click', () => {
        btnUpd.classList.remove('upd-btn-ready')
      }, { once: true })
      if (infoStatus) { infoStatus.textContent = `v${data.version} available`; infoStatus.style.color = 'var(--green)' }
      return
    }

    // ── Step 2: auto-download ──────────────────────────────────────────────
    state = 'downloading'
    pendingVersion = data.version
    btnUpd.textContent = `⬇  Загрузка v${data.version}… 0%`
    btnUpd.classList.add('upd-btn-downloading')
    btnUpd.disabled = true
    progressWrap.style.display = 'flex'
    setProgress(0)
    if (infoStatus) { infoStatus.textContent = `v${data.version} available`; infoStatus.style.color = 'var(--green)' }

    const dl = await window.electronAPI.downloadUpdate(data.download_url)

    if (!dl || !dl.ok) {
      state = 'idle'
      btnUpd.textContent = '⚠  Ошибка загрузки — повторить'
      btnUpd.classList.remove('upd-btn-downloading')
      btnUpd.disabled = false
      progressWrap.style.display = 'none'
      return
    }

    // ── Step 3: ready to install ───────────────────────────────────────────
    state = 'ready'
    installerPath = dl.path
    setProgress(100)
    setTimeout(() => { progressWrap.style.display = 'none' }, 600)
    btnUpd.textContent = '▶  Установить обновление'
    btnUpd.classList.remove('upd-btn-downloading')
    btnUpd.classList.add('upd-btn-install')
    btnUpd.disabled = false
  })
})()

// ── Quick Patches ─────────────────────────────────────────────────────────────
;(function () {
  const btnPatches = document.getElementById('btn-check-patches')
  const patchList  = document.getElementById('patch-list')
  if (!btnPatches) return

  btnPatches.addEventListener('click', async () => {
    btnPatches.textContent = '⏳  Загрузка...'
    btnPatches.disabled = true

    const result = await window.electronAPI.fetchPatches()
    btnPatches.disabled = false
    btnPatches.textContent = '⚡  Проверить патчи'

    if (!result || !result.ok) {
      patchList.innerHTML = '<div class="patch-msg red">⚠  Не удалось загрузить патчи</div>'
      return
    }

    const patches  = (result.data && result.data.quick_patches) || []
    const applied  = JSON.parse(localStorage.getItem('applied-patches') || '[]')
    const pending  = patches.filter(p => !applied.includes(p.id))

    if (pending.length === 0) {
      patchList.innerHTML = '<div class="patch-msg">✓  Все патчи уже применены</div>'
      return
    }

    patchList.innerHTML = ''
    pending.forEach(patch => {
      const row = document.createElement('div')
      row.className = 'patch-item'
      row.innerHTML = `
        <div class="patch-info">
          <span class="patch-title">${patch.title || patch.id}</span>
          ${patch.description ? `<span class="patch-desc">${patch.description}</span>` : ''}
        </div>
        <button class="patch-apply-btn">Применить</button>`
      patchList.appendChild(row)

      row.querySelector('.patch-apply-btn').addEventListener('click', () => {
        if (patch.type === 'settings' && patch.changes) {
          applySettings(patch.changes)
        }
        const saved = JSON.parse(localStorage.getItem('applied-patches') || '[]')
        saved.push(patch.id)
        localStorage.setItem('applied-patches', JSON.stringify(saved))
        row.remove()
        if (!patchList.querySelector('.patch-item')) {
          patchList.innerHTML = '<div class="patch-msg green">✓  Все патчи применены</div>'
        }
      })
    })
  })
})()

// ── Close dialog on outside click ────────────────────────────────────────────
profileDialog.addEventListener('click', e => {
  if (e.target === profileDialog) profileDialog.style.display = 'none'
})

// ── UI Scale (zoom) ───────────────────────────────────────────────────────────
;(function () {
  const slider = document.getElementById('range-ui-zoom')
  const lbl    = document.getElementById('lbl-ui-zoom')
  if (!slider) return

  function applyZoom(pct) {
    window.electronAPI.setZoom(pct / 100)
    localStorage.setItem('ui-zoom', String(pct))
    if (lbl) lbl.value = pct + '%'
    updateSliderTrack(slider)
  }

  const saved = parseInt(localStorage.getItem('ui-zoom') || '', 10)
  if (saved >= 75 && saved <= 150) {
    slider.value = saved
    applyZoom(saved)
  } else {
    updateSliderTrack(slider)
    if (lbl) lbl.value = '100%'
  }

  slider.addEventListener('input', () => applyZoom(+slider.value))
})()
