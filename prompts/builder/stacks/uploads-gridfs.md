# Uploads - MongoDB GridFS

This stack runs on MongoDB alone: there is no Supabase project, SDK, key or login, and none is to be added. Uploaded files are kept in MongoDB itself, with GridFS.

If the project selected an image-uploads plugin (Cloudinary, S3, or another), `.agentforge/PLUGIN.md` names it: use exactly that provider instead. With no plugin selected, keep images and other uploaded files in GridFS on the connection the application already uses (`new mongoose.mongo.GridFSBucket(connection.db, { bucketName })`, or the driver's `GridFSBucket`): one bucket per kind of file, and only the file's `_id` stored in the owning document.

Receive uploads on the server only. Check type and size before writing anything, stream the file into the bucket, and serve it through a route that checks who is asking (set `Content-Type`, `Content-Length` and a sensible `Cache-Control`: public files may be cached, private ones are not). Delete the GridFS file when its document is deleted. Tests use the project's own `_test` database like every other collection. Never write uploads to the local disk as the production answer.
