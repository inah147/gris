// Gera o bundle do Toast UI Editor usado no portal.
//
// O build ESM do @toast-ui/editor (3.2.2, sem manutenção desde 2023) traz uma
// cópia do DOMPurify 2.3.3 embutida no próprio arquivo, com XSS conhecidos já
// corrigidos no 3.x. Como a cópia é inline, o `overrides` do package.json não a
// alcança: este plugin troca, na hora do bundle, a instância embutida pelo
// DOMPurify do node_modules. O editor só usa `purify.sanitize()` com opções que
// o 3.x mantém (ADD_TAGS, ADD_ATTR, FORBID_TAGS, RETURN_DOM_FRAGMENT).
import { readFile } from "node:fs/promises";
import { build } from "esbuild";

const [entry, outfile] = process.argv.slice(2);
if (!entry || !outfile) {
  console.error("uso: node build-toastui-editor.mjs <entry.js> <saida.min.js>");
  process.exit(1);
}

const INSTANCIA_EMBUTIDA = "var purify = createDOMPurify();";

const dompurifyAtual = {
  name: "dompurify-atual",
  setup(b) {
    b.onLoad(
      { filter: /@toast-ui[\\/]editor[\\/]dist[\\/]esm[\\/]index\.js$/ },
      async (args) => {
        const fonte = await readFile(args.path, "utf8");
        if (!fonte.includes(INSTANCIA_EMBUTIDA)) {
          // Versão nova do editor mudou o código: falhar em vez de gerar um
          // bundle que volte a usar a cópia antiga sem ninguém perceber.
          throw new Error(
            `"${INSTANCIA_EMBUTIDA}" não encontrado em ${args.path}`
          );
        }
        const contents =
          'import __grisDOMPurify from "dompurify";\n' +
          fonte.replace(INSTANCIA_EMBUTIDA, "var purify = __grisDOMPurify;");
        return { contents, loader: "js" };
      }
    );
  },
};

await build({
  entryPoints: [entry],
  outfile,
  bundle: true,
  minify: true,
  legalComments: "none",
  platform: "browser",
  format: "iife",
  plugins: [dompurifyAtual],
});
