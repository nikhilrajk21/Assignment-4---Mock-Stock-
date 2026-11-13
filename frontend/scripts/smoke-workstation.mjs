import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const runner = fileURLToPath(new URL('./smoke-live.mjs', import.meta.url))
const env = { ...process.env }
env.OPENAI_API_KEY = ''
for (const scenario of ['--sma', '--chart-decision', '--automation', '--voice']) {
  console.log('Workstation smoke test ' + scenario)
  const run = spawnSync(process.execPath, [runner, scenario], { env, stdio: 'inherit' })
  if (run.error) throw run.error
  if (run.status !== 0) process.exit(run.status ?? 1)
}
console.log('PASS: workstation smoke test')
