// engine client：把 my-worker + micro-plum + deps 打成自包含 IIFE。
// worker.js 源码内联为文本，blob 出 Web Worker（绕过同源），引擎从 CDN 拉 rime.js/wasm/data。
import { LambdaWorker, asyncFS } from '@libreservice/my-worker'
import { Recipe, GitHubDownloader } from '@libreservice/micro-plum'
import workerSrc from './worker-content.txt'

async function makeBlobWorker() {
  const blob = new Blob([workerSrc], { type: 'text/javascript' })
  return URL.createObjectURL(blob)
}

async function ensureDir(FS: any, path: string) {
  let i = 1
  while ((i = path.indexOf('/', i) + 1) > 0) {
    const dir = path.slice(0, i)
    try { await FS.lstat(dir) } catch { await FS.mkdir(dir) }
  }
}

function expose(name: string, fn: any): void {
  const g = window as any
  g.__rimeEngine = g.__rimeEngine || {}
  g.__rimeEngine[name] = fn
}

async function boot() {
  const g = window as any
  const worker = new LambdaWorker(await makeBlobWorker())
  const FS = asyncFS(worker)
  const setIME = worker.register('setIME')
  const setPageSize = worker.register('setPageSize')
  const deploy = worker.register('deploy')
  const processFn = worker.register('process')
  const select = worker.register('selectCandidateOnCurrentPage')
  const reset = worker.register('resetUserDirectory')
  const RIME_PATH = '/rime'

  expose('ready', () => !!g.__rimeEngine && g.__rimeEngine._ready)
  expose('process', (input: string) => processFn(String(input)).then((r: any) => JSON.stringify(r)))
  expose('select', (idx: number) => select(idx))
  expose('setIME', (id: string) => setIME(id))
  expose('reset', () => reset())

  expose('deployWusong', async () => {
    try {
      const downloader = new GitHubDownloader('iDvel/rime-ice', ['rime_ice'])
      const recipe = new Recipe(downloader, { onLoadFailure: (u: string, r: any) => console.error('rime-ice dl-fail', u, r) })
      const manifest = await recipe.load()
      for (const { file, content } of manifest) {
        if (!content) continue
        const path = `${RIME_PATH}/${file}`
        try { await ensureDir(FS, path); await FS.writeFile(path, content) } catch {}
      }
      try { await FS.writeFile(`${RIME_PATH}/default.custom.yaml`, 'patch:\n  schema_list:\n    - schema: rime_ice\n') } catch {}
      await deploy()
      await setIME('rime_ice')
      setPageSize(10)
      g.__rimeEngine._ready = true
      return 'ok'
    } catch (e: any) {
      console.error('deployWusong ERR', e)
      return 'ERR ' + (e && e.message || e)
    }
  })
  expose('_ready', false)
}

boot()