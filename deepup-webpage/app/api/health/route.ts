import { runtimeEnv } from '@/lib/auth';

export async function GET() {
  const env = runtimeEnv();
  return Response.json({
    ok: true,
    bindings: {
      database: Boolean(env.DB),
      media: Boolean(env.MEDIA),
      replicateToken: Boolean(env.REPLICATE_API_TOKEN),
      replicateVersion: Boolean(env.REPLICATE_VERSION),
    },
  });
}
