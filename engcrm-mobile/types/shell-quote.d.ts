declare module "shell-quote" {
  export function quote(tokens: (string | { comment: string })[]): string;
  export function parse(command: string): unknown[];
}
