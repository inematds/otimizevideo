// Baixa as .woff2 do Google Fonts e gera assets/fonts/fonts.css (@font-face local).
import { mkdirSync, writeFileSync } from "node:fs";
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36";
const families = [
  "Sora:wght@700;800",
  "Inter:wght@400;500;600;700",
  "JetBrains+Mono:wght@400;600;700",
];
const url = "https://fonts.googleapis.com/css2?family=" + families.join("&family=") + "&display=block";
mkdirSync(new URL("./assets/fonts/", import.meta.url), { recursive: true });

const css = await (await fetch(url, { headers: { "User-Agent": UA } })).text();
const blocks = css.split("@font-face").slice(1);
let out = "";
let n = 0;
const seen = new Set();
for (const b of blocks) {
  // só o subset "latin" (cobre PT-BR: á à â ã é ê í ó ô õ ú ç).
  // NÃO usar o comentário /* latin */ — o split por "@font-face" joga o comentário
  // do bloco SEGUINTE no chunk do anterior (off-by-one) e acaba baixando o latin-ext.
  // O unicode-range está DENTRO do próprio bloco → é o teste confiável.
  const isLatin = /unicode-range:[^;]*U\+0000-00FF/.test(b);
  if (!isLatin) continue;
  const fam = b.match(/font-family:\s*'([^']+)'/);
  const wght = b.match(/font-weight:\s*(\d+)/);
  const src = b.match(/url\((https:[^)]+\.woff2)\)/);
  const style = b.match(/font-style:\s*(\w+)/);
  if (!fam || !src) continue;
  const key = `${fam[1]}-${wght ? wght[1] : "400"}`;
  if (seen.has(key)) continue;
  seen.add(key);
  const file = `${fam[1].replace(/\s+/g, "")}-${wght ? wght[1] : "400"}.woff2`;
  const buf = Buffer.from(await (await fetch(src[1], { headers: { "User-Agent": UA } })).arrayBuffer());
  writeFileSync(new URL(`./assets/fonts/${file}`, import.meta.url), buf);
  out += `@font-face{font-family:'${fam[1]}';font-style:${style ? style[1] : "normal"};font-weight:${wght ? wght[1] : 400};font-display:block;src:url('./fonts/${file}') format('woff2');}\n`;
  n++;
  console.log("baixei", file, buf.length, "bytes");
}
writeFileSync(new URL("./assets/fonts/fonts.css", import.meta.url), out);
console.log(`OK · ${n} arquivos · fonts.css gerado`);
