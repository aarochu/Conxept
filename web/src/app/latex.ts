import { Directive, ElementRef, effect, inject, input } from '@angular/core';
import katex from 'katex';

/**
 * Renders a LaTeX string into the host element with KaTeX. `fullSize` keeps the math inline but
 * draws fractions and exponents at display size, for answers that must be readable at a glance.
 */
@Directive({ selector: '[latex]' })
export class Latex {
  readonly latex = input<string>('');
  readonly display = input(false);
  readonly fullSize = input(false);
  private readonly el = inject<ElementRef<HTMLElement>>(ElementRef);

  constructor() {
    effect(() => {
      const tex = this.latex() || '';
      katex.render(this.fullSize() && tex ? `\\displaystyle ${tex}` : tex, this.el.nativeElement, {
        throwOnError: false,
        displayMode: this.display(),
        output: 'htmlAndMathml',
      });
    });
  }
}
