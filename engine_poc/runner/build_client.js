const esbuild = require('esbuild')
esbuild.build({
  entryPoints: ['client.ts'],
  bundle: true,
  format: 'iife',
  loader: { '.txt': 'text' },
  outfile: 'serve/engine-client.js',
  logLevel: 'info'
}).catch(e => { console.error(e); process.exit(1) })