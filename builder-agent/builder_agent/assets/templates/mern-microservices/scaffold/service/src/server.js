import { createApp } from './app.js';
import { loadConfig } from './config.js';
import { connectDb } from './db.js';

// The only file that binds a port. scripts/dev-all.mjs looks for exactly this
// path when it discovers the services to start.
const config = loadConfig();
await connectDb(config.mongoUri);
createApp().listen(config.port, '127.0.0.1', () => {
  console.log('service listening on ' + config.port);
});
