// The app's icon as a Windows .ico: one 256×256 PNG image inside an ICO container (Windows Vista and later read it).
// Usage: node release/make-icon.mjs <in.png> <out.ico>
import fs from 'node:fs'

const [input, output] = process.argv.slice(2)
const png = fs.readFileSync(input)
if (png.readUInt32BE(0) !== 0x89504e47) throw new Error(`${input} is not a PNG`)
const width = png.readUInt32BE(16)
const height = png.readUInt32BE(20)
if (width > 256 || height > 256) throw new Error('the PNG must be at most 256×256')
const header = Buffer.alloc(6)
header.writeUInt16LE(0, 0)          // reserved
header.writeUInt16LE(1, 2)          // 1 = icon
header.writeUInt16LE(1, 4)          // one image
const entry = Buffer.alloc(16)
entry.writeUInt8(width === 256 ? 0 : width, 0)
entry.writeUInt8(height === 256 ? 0 : height, 1)
entry.writeUInt8(0, 2)              // no palette
entry.writeUInt8(0, 3)
entry.writeUInt16LE(1, 4)           // colour planes
entry.writeUInt16LE(32, 6)          // bits per pixel
entry.writeUInt32LE(png.length, 8)
entry.writeUInt32LE(header.length + entry.length, 12)
fs.writeFileSync(output, Buffer.concat([header, entry, png]))
console.log(`${output}: ${width}×${height}, ${png.length + 22} bytes`)
