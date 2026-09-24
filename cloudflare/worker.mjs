// Dedicated Cat Stats relay. Never use the Bambu namespace or keys.
export default {
  async fetch(request, env) {
    const reply = (data, status = 200) => Response.json(data, {
      status, headers: {'Cache-Control': 'no-store'}
    });
    const path = new URL(request.url).pathname;
    const key = request.headers.get('x-api-key');
    if (path === '/status' && request.method === 'GET') {
      if (!env.READ_KEY || key !== env.READ_KEY) return reply({error:'unauthorized'},401);
      const data = await env.CAT_STATS.get('status', 'json');
      if (!data) return reply({error:'no data'},503);
      return reply({...data, stale: Date.now()/1000 - data.generated_at > 900});
    }
    if (path === '/ingest' && request.method === 'POST') {
      if (!env.WRITE_KEY || key !== env.WRITE_KEY) return reply({error:'unauthorized'},401);
      // Bound the body while streaming, including requests without Content-Length.
      if (!request.body) return reply({error:'missing body'},400);
      const reader = request.body.getReader();
      const chunks = []; let length = 0;
      while (true) {
        const {done,value} = await reader.read(); if (done) break;
        length += value.byteLength;
        if (length > 65536) { await reader.cancel(); return reply({error:'too large'},413); }
        chunks.push(value);
      }
      let data;
      try {
        const body = new Uint8Array(length); let offset = 0;
        for (const chunk of chunks) {body.set(chunk,offset); offset += chunk.length;}
        data = JSON.parse(new TextDecoder().decode(body));
      } catch {return reply({error:'invalid JSON'},400);}
      if (!data || data.schema_version !== 1 || !Number.isFinite(data.generated_at) ||
          data.generated_at > Date.now()/1000 + 60 || data.generated_at < Date.now()/1000 - 900 ||
          !Array.isArray(data.devices) || !Array.isArray(data.pets) || !Array.isArray(data.alerts)) {
        return reply({error:'invalid snapshot'},400);
      }
      await env.CAT_STATS.put('status', JSON.stringify(data));
      return reply({ok:true});
    }
    return reply({error:'not found'},404);
  }
};
