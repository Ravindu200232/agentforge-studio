// Curated languages for the SRS interview and planning process.
export const COMMON_LANGUAGES = [
  { code: 'en', name: 'English' },
  { code: 'si', name: 'Sinhala (සිංහල)' },
  { code: 'ta', name: 'Tamil (தமிழ்)' },
  { code: 'es', name: 'Spanish (Español)' },
  { code: 'fr', name: 'French (Français)' },
  { code: 'de', name: 'German (Deutsch)' },
  { code: 'zh', name: 'Chinese (中文)' },
  { code: 'ja', name: 'Japanese (日本語)' },
  { code: 'ko', name: 'Korean (한국어)' },
  { code: 'hi', name: 'Hindi (हिन्दी)' },
  { code: 'ar', name: 'Arabic (العربية)' },
  { code: 'pt', name: 'Portuguese (Português)' },
  { code: 'ru', name: 'Russian (Русский)' },
  { code: 'it', name: 'Italian (Italiano)' },
  { code: 'nl', name: 'Dutch (Nederlands)' },
  { code: 'tr', name: 'Turkish (Türkçe)' },
  { code: 'pl', name: 'Polish (Polski)' },
  { code: 'sv', name: 'Swedish (Svenska)' },
  { code: 'id', name: 'Indonesian (Bahasa Indonesia)' },
  { code: 'vi', name: 'Vietnamese (Tiếng Việt)' },
  { code: 'th', name: 'Thai (ไทย)' },
  { code: 'bn', name: 'Bengali (বাংলা)' },
  { code: 'ur', name: 'Urdu (اردو)' },
  { code: 'ms', name: 'Malay (Bahasa Melayu)' },
  { code: 'fa', name: 'Persian (فارسی)' },
  { code: 'el', name: 'Greek (Ελληνικά)' },
  { code: 'he', name: 'Hebrew (עברית)' },
  { code: 'da', name: 'Danish (Dansk)' },
  { code: 'fi', name: 'Finnish (Suomi)' },
  { code: 'no', name: 'Norwegian (Norsk)' },
  { code: 'cs', name: 'Czech (Čeština)' },
  { code: 'ro', name: 'Romanian (Română)' },
  { code: 'hu', name: 'Hungarian (Magyar)' },
  { code: 'uk', name: 'Ukrainian (Українська)' },
]

export const SRS_LANGUAGES = COMMON_LANGUAGES

export function displaySrsLanguages() {
  const preferredCodes = ['en', 'si', 'ta']
  const preferred = COMMON_LANGUAGES.filter(l => preferredCodes.includes(l.code))
  const rest = COMMON_LANGUAGES.filter(l => !preferredCodes.includes(l.code))
    .sort((a, b) => a.name.localeCompare(b.name))

  return [...preferred, ...rest]
}
