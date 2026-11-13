export const GUEST_POLICY = {
  allowImage: true,
  allowVideo: false,
  maxBytes: 10 * 1024 * 1024,
  maxFiles: 1,
  saveHistory: false,
  originalDownload: false,
  modelSelection: false,
} as const;

export const MEMBER_POLICY = {
  allowImage: true,
  allowVideo: true,
  maxBytes: 500 * 1024 * 1024,
  maxFiles: 1,
  saveHistory: true,
  originalDownload: true,
  modelSelection: true,
} as const;

export type AccessPolicy = typeof GUEST_POLICY | typeof MEMBER_POLICY;

export function policyFor(user: unknown): AccessPolicy {
  return user ? MEMBER_POLICY : GUEST_POLICY;
}
