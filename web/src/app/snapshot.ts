import { fromJson, type JsonValue } from '@bufbuild/protobuf';
import { Code, ConnectError, createRouterTransport, type Transport } from '@connectrpc/connect';

import {
  AnalyzeClassResponseSchema,
  GatewayService,
  GatewayServiceGenerateRemediationResponseSchema,
  GatewayServiceListMisconceptionsResponseSchema,
  GatewayServiceListProblemsResponseSchema,
  GetClustersResponseSchema,
  GetEvaluationResponseSchema,
  GetHeatmapResponseSchema,
  GetSubmissionResponseSchema,
  ListClassesResponseSchema,
} from '../gen/misconception/v1/gateway_pb';

/**
 * A read-only snapshot of one processed class, captured from a live gateway by
 * `gateway/cmd/snapshot`. When `snapshot.json` is deployed next to the app, every RPC is
 * answered from it in the browser, so the site needs no backend. Seeding and live checking
 * need the engine and report that instead.
 */
export interface Snapshot {
  capturedAt: string;
  listProblems: JsonValue;
  listMisconceptions: JsonValue;
  listClasses: JsonValue;
  heatmap: JsonValue;
  clusters: JsonValue;
  evaluation: JsonValue;
  submissions: Record<string, JsonValue>;
  remediation: Record<string, JsonValue>;
  analyze: JsonValue[];
}

let loaded: Snapshot | undefined;

export function snapshot(): Snapshot | undefined {
  return loaded;
}

/** Load `snapshot.json` if this deployment ships one. A live gateway answers it with the app shell. */
export async function loadSnapshot(): Promise<void> {
  try {
    const res = await fetch('snapshot.json', { cache: 'no-cache' });
    if (res.ok && (res.headers.get('content-type') ?? '').includes('json')) {
      loaded = (await res.json()) as Snapshot;
    }
  } catch {
    loaded = undefined;
  }
}

const needsEngine = (what: string) =>
  new ConnectError(
    `${what} needs the live engine. This is a read-only snapshot of a processed demo class.`,
    Code.Unimplemented,
  );

const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function snapshotTransport(s: Snapshot): Transport {
  return createRouterTransport((router) => {
    router.service(GatewayService, {
      listProblems: () => fromJson(GatewayServiceListProblemsResponseSchema, s.listProblems),
      listMisconceptions: () =>
        fromJson(GatewayServiceListMisconceptionsResponseSchema, s.listMisconceptions),
      listClasses: () => fromJson(ListClassesResponseSchema, s.listClasses),
      getHeatmap: () => fromJson(GetHeatmapResponseSchema, s.heatmap),
      getClusters: () => fromJson(GetClustersResponseSchema, s.clusters),
      getEvaluation: () => fromJson(GetEvaluationResponseSchema, s.evaluation),
      getSubmission: (req) => {
        const sub = s.submissions[req.submissionId];
        if (!sub) throw new ConnectError('not in this snapshot', Code.NotFound);
        return fromJson(GetSubmissionResponseSchema, sub);
      },
      generateRemediation: (req) => {
        const rem = s.remediation[req.misconceptionId];
        if (!rem)
          throw new ConnectError('no practice captured for this misconception', Code.NotFound);
        return fromJson(GatewayServiceGenerateRemediationResponseSchema, rem);
      },
      async *processClass() {
        yield { done: 480, total: 480 };
      },
      async *analyzeClass() {
        // Replays the captured agent run at a readable pace.
        for (const ev of s.analyze) {
          await pause(350);
          yield fromJson(AnalyzeClassResponseSchema, ev);
        }
      },
      seedSyntheticClass: () => {
        throw needsEngine('Seeding a class');
      },
      tryDerivation: () => {
        throw needsEngine('Checking a derivation');
      },
    });
  });
}
