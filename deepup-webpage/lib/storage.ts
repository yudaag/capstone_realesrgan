import { AwsClient } from 'aws4fetch';
import { runtimeEnv } from '@/lib/auth';

function storageConfig() {
  const env = runtimeEnv();
  const values = {
    accountId: env.R2_ACCOUNT_ID?.trim(),
    bucket: env.R2_BUCKET_NAME?.trim(),
    accessKeyId: env.R2_ACCESS_KEY_ID?.trim(),
    secretAccessKey: env.R2_SECRET_ACCESS_KEY?.trim(),
  };
  if (Object.values(values).some((value) => !value)) throw new Error('R2 API 환경변수가 설정되지 않았습니다.');
  if (!/^[a-f0-9]{32}$/i.test(values.accountId!)) {
    throw new Error('R2_ACCOUNT_ID 형식이 올바르지 않습니다. Cloudflare의 32자리 Account ID만 입력해 주세요.');
  }
  if (!/^[a-z0-9._-]{3,63}$/i.test(values.bucket!)) {
    throw new Error('R2_BUCKET_NAME 형식이 올바르지 않습니다.');
  }
  return values as Record<keyof typeof values, string>;
}

export const mediaBucket = () => runtimeEnv().MEDIA;

export async function signedObjectUrl(key: string, method: 'GET' | 'PUT', contentType?: string) {
  const config = storageConfig();
  const client = new AwsClient({
    accessKeyId: config.accessKeyId,
    secretAccessKey: config.secretAccessKey,
    service: 's3',
    region: 'auto',
  });
  const encodedKey = key.split('/').map(encodeURIComponent).join('/');
  const url = new URL(`https://${config.accountId}.r2.cloudflarestorage.com/${config.bucket}/${encodedKey}`);
  url.searchParams.set('X-Amz-Expires', '3600');
  const signed = await client.sign(url.toString(), {
    method,
    headers: contentType ? { 'Content-Type': contentType } : undefined,
    aws: { signQuery: true },
  });
  return signed.url;
}

export function safeFileName(name: string) {
  const cleaned = name.normalize('NFKC').replace(/[^a-zA-Z0-9._-]+/g, '_').replace(/^\.+/, '');
  return cleaned.slice(-120) || 'upload.bin';
}
