const extensionTypes: Record<string, string> = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
  mp4: 'video/mp4',
  mov: 'video/quicktime',
};

export function mediaContentType(name: string, reportedType?: string | null) {
  const normalized = reportedType?.trim().toLowerCase();
  if (normalized && normalized !== 'application/octet-stream') return normalized;

  const extension = name.split('.').pop()?.toLowerCase() || '';
  return extensionTypes[extension] || 'application/octet-stream';
}
