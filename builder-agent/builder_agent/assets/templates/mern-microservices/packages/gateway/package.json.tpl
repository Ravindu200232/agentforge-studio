{
  "name": "gateway",
  "private": true,
  "type": "module",
  "main": "src/server.js",
  "scripts": {
    "start": "node src/server.js",
    "test": "vitest run"
  },
  "dependencies": {
    "express": "^4.21.2",
    "bcryptjs": "^2.4.3",
    "jsonwebtoken": "^9.0.2"
  },
  "devDependencies": {
    "supertest": "^7.0.0",
    "vitest": "^2.1.8"
  }
}
