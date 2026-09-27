import { describe, it, expect, beforeAll, afterAll, beforeEach } from 'vitest';
import { connectTestDb, clearCollections, closeTestDb, request } from 'testing';
import { createApp } from '../src/app.js';

const app = createApp();

beforeAll(() => connectTestDb());
afterAll(() => closeTestDb());
// Between tests, not once per file: a document left behind changes the next
// test's result, and that failure reads as a product bug.
beforeEach(() => clearCollections());

describe('items', () => {
  it('lists nothing before anything exists', async () => {
    const response = await request(app).get('/items').expect(200);
    expect(response.body.items).toEqual([]);
  });

  it('creates one and returns the public shape', async () => {
    const response = await request(app).post('/items').send({ slug: 'first', name: 'First' }).expect(201);
    expect(response.body.item).toEqual({ id: expect.any(String), slug: 'first', name: 'First', status: 'active' });
  });

  it('rejects a create without the required fields', async () => {
    await request(app).post('/items').send({ name: 'No slug' }).expect(400);
  });

  it('rejects a duplicate slug with a conflict, not a 500', async () => {
    await request(app).post('/items').send({ slug: 'first', name: 'First' }).expect(201);
    await request(app).post('/items').send({ slug: 'first', name: 'Again' }).expect(409);
  });

  it('filters by name, case-insensitively', async () => {
    await request(app).post('/items').send({ slug: 'alpha', name: 'Alpha' }).expect(201);
    await request(app).post('/items').send({ slug: 'beta', name: 'Beta' }).expect(201);
    const response = await request(app).get('/items?q=alp').expect(200);
    expect(response.body.items.map((item) => item.slug)).toEqual(['alpha']);
  });

  it('404s for a slug that does not exist', async () => {
    await request(app).get('/items/missing').expect(404);
    await request(app).patch('/items/missing').send({ status: 'archived' }).expect(404);
    await request(app).delete('/items/missing').expect(404);
  });

  it('changes status and then deletes', async () => {
    await request(app).post('/items').send({ slug: 'first', name: 'First' }).expect(201);
    const patched = await request(app).patch('/items/first').send({ status: 'archived' }).expect(200);
    expect(patched.body.item.status).toBe('archived');
    await request(app).delete('/items/first').expect(204);
    await request(app).get('/items/first').expect(404);
  });

  it('rejects an unknown status', async () => {
    await request(app).post('/items').send({ slug: 'first', name: 'First' }).expect(201);
    await request(app).patch('/items/first').send({ status: 'nonsense' }).expect(400);
  });
});
