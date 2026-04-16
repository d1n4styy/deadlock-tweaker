const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const http  = require('http')
const https = require('https')
const fs    = require('fs')
const os    = require('os')

let mainWindow
let pythonProcess
const BACKEND_PORT = 7654

// When packaged, electron-builder puts extraResources into process.resourcesPath
const IS_PACKAGED = app.isPackaged
const VENV_PYTHON = IS_PACKAGED
  ? path.join(process.resourcesPath, '.venv', 'Scripts', 'python.exe')
  : path.join(__dirname, '..', '.venv', 'Scripts', 'python.exe')
const SERVER_SCRIPT = IS_PACKAGED
  ? path.join(process.resourcesPath, 'app', 'backend', 'server.py')
  : path.join(__dirname, 'backend', 'server.py')

function waitForBackend(retries = 20) {
  return new Promise((resolve, reject) => {
    const try_ = (n) => {
      const req = http.get(`http://127.0.0.1:${BACKEND_PORT}/api/version`, (res) => {
        resolve()
      })
      req.on('error', () => {
        if (n <= 0) return reject(new Error('Backend did not start'))
        setTimeout(() => try_(n - 1), 300)
      })
      req.end()
    }
    try_(retries)
  })
}

function startPython() {
  pythonProcess = spawn(VENV_PYTHON, [SERVER_SCRIPT], {
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  })
  pythonProcess.stdout.on('data', (d) => process.stdout.write(`[py] ${d}`))
  pythonProcess.stderr.on('data', (d) => process.stderr.write(`[py-err] ${d}`))
  pythonProcess.on('exit', (code) => {
    if (code !== null && code !== 0) console.error(`Python exited with code ${code}`)
  })
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1160,
    height: 740,
    minWidth: 900,
    minHeight: 660,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: true,
    resizable: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'))
  // mainWindow.webContents.openDevTools({ mode: 'detach' })

  mainWindow.on('closed', () => { mainWindow = null })

  function sendMaximizeState() {
    if (!mainWindow) return
    mainWindow.webContents.send('maximize-change', mainWindow.isMaximized())
  }
  mainWindow.on('maximize', sendMaximizeState)
  mainWindow.on('unmaximize', sendMaximizeState)
}

// Window control IPC
ipcMain.on('window-minimize', () => mainWindow && mainWindow.minimize())
ipcMain.on('window-maximize', () => {
  if (!mainWindow) return
  if (mainWindow.isMaximized()) {
    mainWindow.unmaximize()
  } else {
    mainWindow.maximize()
  }
})

ipcMain.on('window-close', () => mainWindow && mainWindow.close())
ipcMain.handle('window-is-maximized', () => mainWindow ? mainWindow.isMaximized() : false)

// File dialog for autoexec
ipcMain.handle('open-file-dialog', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: 'Выберите autoexec.cfg',
    filters: [{ name: 'Config Files', extensions: ['cfg'] }, { name: 'All Files', extensions: ['*'] }],
    properties: ['openFile'],
  })
  return result.canceled ? null : result.filePaths[0]
})

// ── Update: download installer ────────────────────────────────────────────────
function downloadFile(url, dest, onProgress) {
  return new Promise((resolve, reject) => {
    const attempt = (currentUrl, hops = 0) => {
      if (hops > 10) return reject(new Error('Too many redirects'))
      const mod = currentUrl.startsWith('https') ? https : http
      mod.get(currentUrl, { headers: { 'User-Agent': 'DeadlockTweaker-Updater/1.0' } }, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          res.resume()
          return attempt(res.headers.location, hops + 1)
        }
        if (res.statusCode !== 200) {
          res.resume()
          return reject(new Error(`HTTP ${res.statusCode}`))
        }
        const total = parseInt(res.headers['content-length'] || '0', 10)
        let received = 0
        const file = fs.createWriteStream(dest)
        res.on('data', chunk => {
          received += chunk.length
          if (total > 0) onProgress(Math.round((received / total) * 100))
        })
        res.pipe(file)
        file.on('finish', () => file.close(() => resolve({ ok: true, path: dest })))
        file.on('error', err => { try { fs.unlinkSync(dest) } catch {} reject(err) })
        res.on('error',  err => { try { fs.unlinkSync(dest) } catch {} reject(err) })
      }).on('error', reject)
    }
    attempt(url)
  })
}

ipcMain.handle('update-download', async (event, downloadUrl) => {
  const dest = path.join(os.tmpdir(), 'DeadlockTweaker-update.exe')
  try {
    const result = await downloadFile(downloadUrl, dest, (pct) => {
      if (mainWindow) mainWindow.webContents.send('update-progress', pct)
    })
    return result
  } catch (e) {
    return { ok: false, error: e.message }
  }
})

// ── Update: run installer & quit ──────────────────────────────────────────────
ipcMain.handle('update-install', async (event, installerPath) => {
  try {
    spawn(installerPath, ['/SILENT', '/CLOSEAPPLICATIONS'], {
      detached: true,
      stdio: 'ignore',
    }).unref()
    setTimeout(() => app.quit(), 800)
    return { ok: true }
  } catch (e) {
    return { ok: false, error: e.message }
  }
})

// ── Patches: fetch patches.json from GitHub raw ───────────────────────────────
ipcMain.handle('patches-fetch', async () => {
  const url = 'https://raw.githubusercontent.com/d1n4styy/deadlock-tweaker/main/patches.json'
  return new Promise((resolve) => {
    https.get(url, { headers: { 'User-Agent': 'DeadlockTweaker/1.0' } }, (res) => {
      if (res.statusCode !== 200) {
        res.resume()
        return resolve({ ok: false, error: `HTTP ${res.statusCode}` })
      }
      let data = ''
      res.on('data', c => data += c)
      res.on('end', () => {
        try { resolve({ ok: true, data: JSON.parse(data) }) }
        catch  { resolve({ ok: false, error: 'JSON parse error' }) }
      })
    }).on('error', e => resolve({ ok: false, error: e.message }))
  })
})

app.whenReady().then(async () => {
  startPython()
  try {
    await waitForBackend()
  } catch (e) {
    console.error('Backend start timeout:', e.message)
  }
  createWindow()
})

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.kill()
    pythonProcess = null
  }
  if (process.platform !== 'darwin') app.quit()
})
