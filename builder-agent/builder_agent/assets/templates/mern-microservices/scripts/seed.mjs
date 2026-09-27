import mongoose from 'mongoose';
import bcrypt from 'bcryptjs';
import { existsSync, readFileSync } from 'node:fs';

let mongoUri = process.env.MONGODB_URI;
if (!mongoUri) {
  for (const file of ['.env.local', '.env']) {
    if (existsSync(file)) {
      const match = readFileSync(file, 'utf8').match(/^\s*(?:export\s+)?MONGODB_URI\s*=\s*['"]?(.*?)['"]?\s*$/m);
      if (match) {
        mongoUri = match[1];
        break;
      }
    }
  }
}
mongoUri = mongoUri || 'mongodb://127.0.0.1:27017/__APP_DB__';

const DEMO_PASSWORD = 'Password1!';
const hashedPassword = bcrypt.hashSync(DEMO_PASSWORD, 10);

const DEMO_USERS = [
  { email: 'admin@demo.test', name: 'Admin Demo', role: 'admin' },
  { email: 'user@demo.test', name: 'User Demo', role: 'user' },
  { email: 'manager@demo.test', name: 'Manager Demo', role: 'manager' },
];

async function seed() {
  try {
    await mongoose.connect(mongoUri);
    const db = mongoose.connection.db;
    const users = db.collection('users');

    for (const user of DEMO_USERS) {
      await users.updateOne(
        { email: user.email },
        {
          $set: {
            email: user.email,
            password: hashedPassword,
            name: user.name,
            role: user.role,
            updatedAt: new Date(),
          },
          $setOnInsert: {
            createdAt: new Date(),
          },
        },
        { upsert: true }
      );
    }
    console.log(`✅ Seeded ${DEMO_USERS.length} demo accounts in ${mongoUri} (password: ${DEMO_PASSWORD})`);
    await mongoose.disconnect();
    process.exit(0);
  } catch (error) {
    console.error('❌ Seed failed:', error.message);
    process.exit(1);
  }
}

seed();
