export const ALLOWED_EXTENSIONS = ['.pdf', '.md', '.txt']
export const ACCEPT_ATTRIBUTE = ALLOWED_EXTENSIONS.join(',')
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024

/** Returns an error message if the file can't be uploaded, otherwise null. */
export function validateFile(file: File): string | null {
  const name = file.name.toLowerCase()
  if (!ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return `Unsupported file type. Allowed: ${ALLOWED_EXTENSIONS.join(', ')}.`
  }
  if (file.size === 0) return 'The file is empty.'
  if (file.size > MAX_UPLOAD_BYTES) {
    return `File is too large. The maximum size is ${MAX_UPLOAD_BYTES / 1024 / 1024} MB.`
  }
  return null
}
