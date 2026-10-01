import { Router } from 'express';
import { Item } from '../models/Item.js';

export const itemsRouter = Router();

itemsRouter.get('/', async (req, res, next) => {
  try {
    const filter = {};
    if (req.query.q) filter.name = { $regex: String(req.query.q), $options: 'i' };
    if (req.query.status) filter.status = String(req.query.status);
    const items = await Item.find(filter).sort({ name: 1 }).limit(100);
    res.json({ items: items.map((item) => item.toPublic()) });
  } catch (error) { next(error); }
});

itemsRouter.post('/', async (req, res, next) => {
  try {
    const { slug, name } = req.body ?? {};
    // Validate untrusted input before the database call; a schema error is a
    // 500 unless it is caught, and the client cannot act on that.
    if (!slug || !name) return res.status(400).json({ error: 'slug and name are required' });
    const item = await Item.create({ slug, name });
    res.status(201).json({ item: item.toPublic() });
  } catch (error) { next(error); }
});

itemsRouter.get('/:slug', async (req, res, next) => {
  try {
    const item = await Item.findOne({ slug: req.params.slug });
    if (!item) return res.status(404).json({ error: 'Item not found' });
    res.json({ item: item.toPublic() });
  } catch (error) { next(error); }
});

itemsRouter.patch('/:slug', async (req, res, next) => {
  try {
    const status = req.body?.status;
    if (!['active', 'archived'].includes(status)) return res.status(400).json({ error: 'unknown status' });
    const item = await Item.findOneAndUpdate({ slug: req.params.slug }, { status }, { new: true });
    if (!item) return res.status(404).json({ error: 'Item not found' });
    res.json({ item: item.toPublic() });
  } catch (error) { next(error); }
});

itemsRouter.delete('/:slug', async (req, res, next) => {
  try {
    const item = await Item.findOneAndDelete({ slug: req.params.slug });
    if (!item) return res.status(404).json({ error: 'Item not found' });
    res.status(204).end();
  } catch (error) { next(error); }
});
