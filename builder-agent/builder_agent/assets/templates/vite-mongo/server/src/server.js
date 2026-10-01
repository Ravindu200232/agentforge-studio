import { createApp } from './app.js';
import { loadConfig } from './config.js';
import { connectDb } from './db.js';

const config = loadConfig();
await connectDb(config.mongodbUri);
createApp().listen(config.port, '127.0.0.1', () => {
  console.log('server listening on http://127.0.0.1:' + config.port);
});
