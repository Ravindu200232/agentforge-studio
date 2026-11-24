# Uploads - Supabase Storage bucket

This stack keeps uploaded files in a Supabase Storage bucket; MongoDB holds the data.

If the project selected an image-uploads plugin (Cloudinary, S3, or another), `.agentforge/PLUGIN.md` names it: use exactly that provider instead. With no plugin selected, keep images and other uploaded files in Supabase Storage.

This project has its own Supabase project, and `SUPABASE_URL`, `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` are already in the environment of every command and of the preview - never ask the customer for them. Add `@supabase/supabase-js` to the server's dependencies and upload from the server with its Storage API into a bucket per kind of file, with access rules for who may upload, read and delete. Store the object path in the MongoDB document, and serve public files by their public URL and private ones through short-lived signed URLs. Check type and size before upload. The service-role key stays on the server: never in browser code, never in a `NEXT_PUBLIC_` or `VITE_` variable. Never write uploads to the local disk as the production answer.
