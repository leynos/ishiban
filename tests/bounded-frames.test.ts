/** @file Preserve independently decoded NDJSON records across arbitrary UTF-8 partitions. */
import {expect, it} from 'bun:test';
import fc from 'fast-check';
import {Schema} from 'effect';
import {readBoundedFrames} from '../src/bounded-frames';

const RecordSchema = Schema.Struct({index: Schema.Number, text: Schema.String});
type RecordFrame = typeof RecordSchema.Type;
const decode = Schema.decodeUnknownSync(RecordSchema);

/** Partition a bounded fixture; for example, a cut inside an emoji divides its UTF-8 bytes. */
function partitionedResponse(bytes: Uint8Array, positions: readonly number[]): Response {
  const boundaries = [...new Set([0, ...positions.map((position) => position % (bytes.length + 1)), bytes.length])];
  const ordered = boundaries.toSorted((left, right) => left - right);
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        let previous = 0;
        for (const boundary of ordered.slice(1)) {
          controller.enqueue(bytes.slice(previous, boundary));
          previous = boundary;
        }
        controller.close();
      }
    })
  );
}

it('emits valid members once and in order regardless of UTF-8 partitioning', async () => {
  const text = fc
    .array(fc.constantFrom('a', '☃', '🙂', '漢', '\n', '\0'), {maxLength: 8})
    .map((parts) => parts.join(''));
  const member = fc.record({
    isValid: fc.boolean(),
    text,
    invalidLine: fc.constantFrom('null', 'not-json', '{"index":"wrong"}')
  });
  const membersArbitrary = fc.array(member, {maxLength: 6});
  const cutsArbitrary = fc.array(fc.nat(), {maxLength: 24});
  await fc.assert(
    fc.asyncProperty(membersArbitrary, cutsArbitrary, fc.boolean(), async (members, cuts, hasFinalNewline) => {
      const first = {index: -1, text: '☃🙂'};
      const last = {index: members.length, text: '漢'};
      const expected = [
        first,
        ...members.flatMap((member, index) => (member.isValid ? [{index, text: member.text}] : [])),
        last
      ];
      const lines = [
        JSON.stringify(first),
        ...members.map((member, index) =>
          member.isValid ? JSON.stringify({index, text: member.text}) : member.invalidLine
        ),
        JSON.stringify(last)
      ];
      const body = `${lines.join('\n')}${hasFinalNewline ? '\n' : ''}`;
      const received: RecordFrame[] = [];
      await readBoundedFrames(
        partitionedResponse(new TextEncoder().encode(body), cuts),
        {maxFrameChars: 1024, maxResponseBytes: 8192, maxResults: 8},
        (line) => decode(JSON.parse(line)),
        (record) => received.push(record)
      );
      expect(received).toEqual(expected);
    })
  );
});
