import { AwsClient } from 'aws4fetch';
import { runtimeEnv } from '@/lib/auth';

function storageConfig() {
  const env = runtimeEnv();
  const values = { accountId: env.R2_ACCOUNT_ID, bucket: env.R2_BUCKET_NAME, accessKeyId: env.R2_ACCESS_KEY_ID, secretAccessKey: env.R2_SECRET_ACCESS_KEY };
  if (Object.values(values).some((value) => !value)) throw new Error('R2 API 환경변수가 설정되지 않았습니다.');
  return values as Record<keyof typeof values, string>;
}

export const mediaBucket = () => runtimeEnv().MEDIA;

export async function signedObjectUrl(key: string, method: 'GET' | 'PUT', contentType?: string) {
  const config = storageConfig();
  const client = new AwsClient({ accessKeyId: config.accessKeyId, secretAccessKey: config.secretAccessKey });
  const encodedKey = key.split('/').map(encodeURIComponent).join('/');
  const url = new URL(`https://${config.accountId}.r2.cloudflarestorage.com/${config.bucket}/${encodedKey}`);
  url.searchParams.set('X-Amz-Expires', '3600');
  const signed = await client.sign(new Request(url, { method, headers: contentType ? { 'Content-Type': contentType } : undefined }), { aws: { signQuery: true } });
  return signed.url;
}

export function safeFileName(name: string) {
  const cleaned = name.normalize('NFKC').replace(/[^a-zA-Z0-9._-]+/g, '_').replace(/^\.+/, '');
  return cleaned.slice(-120) || 'upload.bin';
}
