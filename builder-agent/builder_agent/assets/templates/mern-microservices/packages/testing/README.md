# testing

Shared test helpers. A service suite imports them by package name because it is
a workspace:

    import { connectTestDb, clearCollections, closeTestDb, request } from 'testing';

    beforeAll(() => connectTestDb());
    afterAll(() => closeTestDb());
    beforeEach(() => clearCollections());

    it('lists nothing before anything is created', async () => {
      const response = await request(createApp()).get('/things').expect(200);
      expect(response.body.things).toEqual([]);
    });
