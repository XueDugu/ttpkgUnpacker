#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { TextDecoder } = require('util');

const TEXT_EXTS = new Set(['.js', '.json', '.wxml', '.ttml', '.wxss', '.ttss']);

function normalizePackagePath(name) {
  return String(name || '').replace(/\\/g, '/');
}

function safeJoin(rootDir, relPath) {
  const normalized = normalizePackagePath(relPath);
  if (!normalized || normalized.startsWith('/')) {
    throw new Error(`Unsafe path in package: ${JSON.stringify(relPath)}`);
  }
  const parts = normalized.split('/').filter(Boolean);
  if (!parts.length || parts.includes('..')) {
    throw new Error(`Unsafe path in package: ${JSON.stringify(relPath)}`);
  }
  const absRoot = path.resolve(rootDir);
  const absDest = path.resolve(absRoot, ...parts);
  if (!absDest.startsWith(absRoot + path.sep) && absDest !== absRoot) {
    throw new Error(`Unsafe path escape: ${JSON.stringify(relPath)}`);
  }
  return absDest;
}

function ensureParentDir(destPath) {
  const dir = path.dirname(destPath);
  fs.mkdirSync(dir, { recursive: true });
}

function readU32LE(buf, offset) {
  return buf.readUInt32LE(offset);
}

async function loadArkCrypto() {
  let ark;
  try {
    ark = require(path.join(__dirname, 'vendor', '@byted', 'arkcrypto-minigame-js'));
  } catch (err) {
    // Allow users to provide their own installation if they prefer.
    try {
      ark = require('@byted/arkcrypto-minigame-js');
    } catch (inner) {
      const message = String(inner && inner.message ? inner.message : inner);
      if (message.includes('Cannot find module')) {
        throw new Error(
          "Missing ArkCrypto runtime. Expected vendor copy at " +
            JSON.stringify(path.join(__dirname, 'vendor', '@byted', 'arkcrypto-minigame-js')) +
            " (or install '@byted/arkcrypto-minigame-js' in your Node environment)."
        );
      }
      throw inner;
    }
  }

  ark.enableLog = false;
  await ark.hasDone();
  return ark;
}

function createDecMiniGame(ark, ttksKeyAsciiBytes) {
  if (!Buffer.isBuffer(ttksKeyAsciiBytes) || ttksKeyAsciiBytes.length !== 32) {
    throw new Error(`__ttks key must be 32 bytes (ASCII). Got len=${ttksKeyAsciiBytes?.length}`);
  }

  const keyPtr = ark._malloc(32);
  const lenPtr = ark._malloc(4);
  new Uint8Array(ark.HEAPU8.buffer, keyPtr, 32).set(ttksKeyAsciiBytes);

  let inPtr = 0;
  let outPtr = 0;
  let bufCap = 0;

  function ensureBufCap(n) {
    if (n <= bufCap) return;
    if (inPtr) ark._free(inPtr);
    if (outPtr) ark._free(outPtr);
    inPtr = ark._malloc(n);
    outPtr = ark._malloc(n);
    bufCap = n;
  }

  function dec(buf) {
    const n = buf.length;
    ensureBufCap(n);
    new Uint8Array(ark.HEAPU8.buffer, inPtr, n).set(buf);
    new Uint32Array(ark.HEAPU32.buffer, lenPtr, 1).set([n]);
    ark._decMiniGame(inPtr, n, outPtr, lenPtr, keyPtr);
    return Buffer.from(new Uint8Array(ark.HEAPU8.buffer, outPtr, n));
  }

  function close() {
    if (inPtr) ark._free(inPtr);
    if (outPtr) ark._free(outPtr);
    ark._free(keyPtr);
    ark._free(lenPtr);
  }

  return { dec, close };
}

function parseTtksHeader(pkgBuf) {
  if (pkgBuf.length < 16) throw new Error('Package is too small');
  const tag = pkgBuf.slice(0, 4).toString('ascii');
  if (tag !== 'TPKG') throw new Error(`Unsupported tag: ${JSON.stringify(tag)}`);
  const version = readU32LE(pkgBuf, 4);
  const metadataBlockSize = readU32LE(pkgBuf, 8);
  const metadataLength = readU32LE(pkgBuf, 12);
  const metaStart = 16;
  const metaEnd = metaStart + metadataLength;
  if (metaEnd > pkgBuf.length) throw new Error('metadataLength exceeds file size');
  const metadataRaw = pkgBuf.slice(metaStart, metaEnd);
  if (!metadataRaw.slice(0, 5).equals(Buffer.from('JSON{'))) {
    throw new Error('TPKG does not contain JSON{...} metadata');
  }
  const metadataJson = JSON.parse(metadataRaw.slice(4).toString('utf8'));
  if (!metadataJson || typeof metadataJson.__ttks !== 'string') {
    throw new Error('TPKG JSON header does not include __ttks');
  }
  const ttks = metadataJson.__ttks;
  return {
    tag,
    version,
    metadataBlockSize,
    metadataLength,
    metadataJson,
    ttks,
    indexStart: metaEnd,
  };
}

async function main() {
  const inputPath = process.argv[2];
  const outputDir = process.argv[3];

  if (!inputPath || !outputDir) {
    console.error('Usage: node ttks_unpack.js <input.pkg> <output_dir>');
    process.exit(2);
  }

  const pkgBuf = fs.readFileSync(inputPath);
  const header = parseTtksHeader(pkgBuf);

  const ark = await loadArkCrypto();
  const decoder = new TextDecoder();
  const ttksKey = Buffer.from(header.ttks, 'utf8');
  const decMiniGame = createDecMiniGame(ark, ttksKey);
  try {
    let off = header.indexStart;
    if (off + 4 > pkgBuf.length) throw new Error('Missing entry count');
    const count = readU32LE(pkgBuf, off);
    off += 4;

    const entries = [];
    for (let i = 0; i < count; i++) {
      if (off + 4 > pkgBuf.length) throw new Error(`Entry ${i} name_length out of bounds`);
      const nameLen = readU32LE(pkgBuf, off);
      off += 4;
      const blockLen = nameLen + 8;
      if (off + blockLen > pkgBuf.length) throw new Error(`Entry ${i} encrypted block out of bounds`);
      const encBlock = pkgBuf.slice(off, off + blockLen);
      off += blockLen;

      const decBlock = decMiniGame.dec(encBlock);
      const nameBytes = decBlock.slice(0, nameLen);
      const name = decoder.decode(nameBytes);
      const pos = readU32LE(decBlock, nameLen);
      const size = readU32LE(decBlock, nameLen + 4);
      entries.push({ name, pos, size });
    }

    fs.mkdirSync(outputDir, { recursive: true });

    for (const entry of entries) {
      const name = normalizePackagePath(entry.name);
      if (!name || name.endsWith('/')) continue;

      const pos = entry.pos >>> 0;
      const size = entry.size >>> 0;
      if (pos + size > pkgBuf.length) {
        throw new Error(`Entry out of bounds: ${name} pos=${pos} size=${size} file=${pkgBuf.length}`);
      }

      const dest = safeJoin(outputDir, name);
      const raw = Buffer.from(pkgBuf.slice(pos, pos + size));
      const ext = path.extname(name).toLowerCase();

      if (TEXT_EXTS.has(ext)) {
        for (let base = 0; base < raw.length; base += 8192) {
          const segLen = Math.min(1024, raw.length - base);
          if (segLen <= 0) break;
          const seg = raw.slice(base, base + segLen);
          const dec = decMiniGame.dec(seg);
          dec.copy(raw, base);
        }
      } else {
        const segLen = Math.min(64, raw.length);
        if (segLen > 0) {
          const seg = raw.slice(0, segLen);
          const dec = decMiniGame.dec(seg);
          dec.copy(raw, 0);
        }
      }

      ensureParentDir(dest);
      fs.writeFileSync(dest, raw);
    }
  } finally {
    decMiniGame.close();
  }
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : String(err));
  process.exit(1);
});
