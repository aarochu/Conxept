import { Injectable } from '@angular/core';
import { Code, ConnectError, createClient } from '@connectrpc/connect';
import { createConnectTransport } from '@connectrpc/connect-web';

import { Family, Misconception, Problem } from '../gen/misconception/v1/common_pb';
import { GatewayService } from '../gen/misconception/v1/gateway_pb';
import { snapshot, snapshotTransport } from './snapshot';

/**
 * The one Connect client for the gateway (same origin; `ng serve` proxies to :8080). A deployment
 * that ships `snapshot.json` answers every call from it instead (see snapshot.ts).
 */
@Injectable({ providedIn: 'root' })
export class Api {
  readonly snapshot = snapshot();
  readonly client = createClient(
    GatewayService,
    this.snapshot
      ? snapshotTransport(this.snapshot)
      : createConnectTransport({ baseUrl: window.location.origin }),
  );

  private problemsP?: Promise<Problem[]>;
  private catalogP?: Promise<Map<string, Misconception>>;

  problems(): Promise<Problem[]> {
    this.problemsP ??= this.client.listProblems({}).then(
      (r) => r.problems,
      (e) => {
        this.problemsP = undefined;
        throw e;
      },
    );
    return this.problemsP;
  }

  async problem(id: string): Promise<Problem | undefined> {
    return (await this.problems()).find((p) => p.id === id);
  }

  catalog(): Promise<Map<string, Misconception>> {
    this.catalogP ??= this.client.listMisconceptions({}).then(
      (r) => new Map(r.misconceptions.map((m) => [m.id, m])),
      (e) => {
        this.catalogP = undefined;
        throw e;
      },
    );
    return this.catalogP;
  }
}

export function errorMessage(e: unknown): string {
  if (e instanceof ConnectError) {
    switch (e.code) {
      case Code.Unavailable:
        return 'The gateway or engine is not reachable. Start them with `make engine` and `make gateway`.';
      case Code.FailedPrecondition:
        return 'Analyze needs OPENROUTER_API_KEY (free models work) or ANTHROPIC_API_KEY in the engine’s environment.';
      case Code.NotFound:
        return `Not found: ${e.rawMessage}`;
      default:
        return e.rawMessage || e.message;
    }
  }
  return e instanceof Error ? e.message : String(e);
}

export const FAMILY_NAMES: Record<number, string> = {
  [Family.UNSPECIFIED]: 'Unknown',
  [Family.INVERSE_LAPLACE_PF]: 'Inverse Laplace',
  [Family.CAUSAL_CONVOLUTION]: 'Convolution',
  [Family.FOURIER_TRANSFORM]: 'Fourier transform',
  [Family.LAPLACE_TIME_SHIFT]: 'Laplace time shift',
};

export function pct(n: number, d: number): string {
  return d === 0 ? '—' : `${Math.round((1000 * n) / d) / 10}%`;
}
