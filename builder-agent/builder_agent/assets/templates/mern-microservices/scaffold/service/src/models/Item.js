import mongoose from 'mongoose';

// Rename this model and its fields to the resource this service owns.
const itemSchema = new mongoose.Schema({
  // `unique` declares the index here. Declaring it again with
  // schema.index({ slug: 1 }) makes Mongoose warn about a duplicate index.
  slug: { type: String, required: true, unique: true, trim: true },
  name: { type: String, required: true, trim: true },
  status: { type: String, required: true, enum: ['active', 'archived'], default: 'active' },
}, { timestamps: true });

/** One serializer, so every route in this service returns the same shape. */
itemSchema.methods.toPublic = function toPublic() {
  return { id: String(this._id), slug: this.slug, name: this.name, status: this.status };
};

// A model compiled twice — by a test file and by the app — throws
// OverwriteModelError.
export const Item = mongoose.models.Item ?? mongoose.model('Item', itemSchema);
