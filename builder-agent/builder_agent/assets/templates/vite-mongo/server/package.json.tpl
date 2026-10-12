{
  "name": "server",
  "private": true,
  "type": "module",
  "main": "src/server.js",
  "scripts": {
    "start": "node src/server.js",
    "test": "vitest run"
  },
  "dependencies": {
    "express": "^4.21.2",
    "mongoose": "^8.9.5",
    "bcryptjs": "^2.4.3",
    "jose": "^5.9.6"
  },
  "devDependencies": {
    "supertest": "^7.0.0",
    "vitest": "^2.1.8"
  }
}
