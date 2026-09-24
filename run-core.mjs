// Execute this project's C++ WASI build. No third-party npm dependencies.
import { readFile } from 'node:fs/promises';
import { WASI } from 'node:wasi';
const args = process.argv.slice(2);
const test = args[0] === '--tests';
if (test) args.shift();
const filename = test ? 'flight_tests.wasm' : 'flight_cli.wasm';
const wasi = new WASI({ version: 'preview1', args: [filename, ...args], env: {},
  preopens: { '.': process.cwd() }, returnOnExit: true });
try {
  const module = await WebAssembly.compile(await readFile(new URL('./build/' + filename, import.meta.url)));
  const instance = await WebAssembly.instantiate(module, wasi.getImportObject());
  process.exitCode = wasi.start(instance);
} catch (error) {
  console.error('Não foi possível executar o núcleo C++:', error.message);
  process.exitCode = 1;
}
