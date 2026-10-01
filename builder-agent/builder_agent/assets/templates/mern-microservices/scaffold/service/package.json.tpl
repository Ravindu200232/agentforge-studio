{
  "name": "CHANGE-ME-service",
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
    "jsonwebtoken": "^9.0.2"
  },
  "devDependencies": {
    "testing": "*",
    "vitest": "^2.1.8"
  }
}
