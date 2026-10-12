import { createClient } from '@supabase/supabase-js';

const url = process.env.SUPABASE_URL;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
if (!url || !serviceRoleKey) {
  console.error('❌ SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set (AgentForge sets these '
    + 'automatically when this runs through the Studio).');
  process.exit(1);
}

const admin = createClient(url, serviceRoleKey, { auth: { autoRefreshToken: false, persistSession: false } });

const DEMO_PASSWORD = 'Password1!';
const DEMO_USERS = [
  { email: 'admin@demo.test', name: 'Admin Demo', role: 'admin' },
  { email: 'user@demo.test', name: 'User Demo', role: 'user' },
  { email: 'manager@demo.test', name: 'Manager Demo', role: 'manager' },
];

async function seed() {
  for (const user of DEMO_USERS) {
    // Auth users are the identity; a `profiles` table (created by the app's own migrations) is
    // the usual place for the role and name - this only guarantees the Auth user exists.
    const { error } = await admin.auth.admin.createUser({
      email: user.email, password: DEMO_PASSWORD, email_confirm: true,
      user_metadata: { name: user.name, role: user.role },
    });
    if (error && error.code !== 'email_exists') throw error;
  }
  console.log(`✅ Seeded ${DEMO_USERS.length} demo accounts in ${url} (password: ${DEMO_PASSWORD})`);
}

seed().catch((error) => {
  console.error('❌ Seed failed:', error.message);
  process.exit(1);
});
