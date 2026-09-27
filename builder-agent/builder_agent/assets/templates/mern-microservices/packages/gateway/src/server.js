import { createApp } from './app.js';
import { loadConfig } from './config.js';

const config = loadConfig();
createApp(config).listen(config.port, '127.0.0.1', () => {
  console.log('gateway listening on http://127.0.0.1:' + config.port);
});
