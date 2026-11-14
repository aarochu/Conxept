import { Directive, ElementRef, effect, inject, input } from '@angular/core';
import katex from 'katex';

/** Renders a LaTeX string into the host element with KaTeX. */
@Directive({ selector: '[latex]' })
export class Latex {
  readonly latex = input<string>('');
  readonly display = input(false);
  private readonly el = inject<ElementRef<HTMLElement>>(ElementRef);

  constructor() {
    effect(() => {
      katex.render(this.latex() || '', this.el.nativeElement, {
        throwOnError: false,
        displayMode: this.display(),
        output: 'html',
      });
    });
  }
}
