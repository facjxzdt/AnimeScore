import { build } from 'esbuild';
import { mkdir, copyFile } from 'node:fs/promises';

await mkdir('dist', { recursive: true });
await build({ entryPoints: ['src/app.js', 'src/admin.js'], bundle: true, minify: true, outdir: 'dist', target: 'es2022', legalComments: 'linked' });
await copyFile('src/index.html', 'dist/index.html');
await copyFile('src/style.css', 'dist/style.css');
await copyFile('src/admin.html', 'dist/admin.html');
await copyFile('src/admin.css', 'dist/admin.css');
await copyFile('src/community.css', 'dist/community.css');
