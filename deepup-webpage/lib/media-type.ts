const extensionTypes: Record<string, string> = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
  mp4: 'video/mp4',
  mov: 'video/quicktime',
};

export function mediaContentType(name: string, reportedType?: string | null) {
  const extension = name.split('.').pop()?.toLowerCase() || '';
  const typeFromExtension = extensionTypes[extension];
  if (typeFromExtension) return typeFromExtension;

  const normalized = reportedType?.split(';')[0]?.trim().toLowerCase();
  const aliases: Record<string, string> = {
    'image/jpg': 'image/jpeg',
    'image/pjpeg': 'image/jpeg',
    'image/x-png': 'image/png',
    'video/x-m4v': 'video/mp4',
  };

  if (normalized && normalized !== 'application/octet-stream') {
    return aliases[normalized] || normalized;
  }
  return 'application/octet-stream';
}
