const esbuild = require('esbuild');
const fs = require('fs');
const path = require('path');

const isWatch = process.argv.includes('--watch');

// Build 1: Main plugin sandbox code
const mainBuildOptions = {
  entryPoints: ['src/main.ts'],
  bundle: true,
  outfile: 'dist/main.js',
  format: 'iife',
  target: 'es6',
  sourcemap: false,
  minify: !isWatch,
  logLevel: 'info',
};

// Build 2: UI code - bundled into a single JS string, then inlined into ui.html
const uiBuildOptions = {
  entryPoints: ['src/ui.ts'],
  bundle: true,
  outfile: 'dist/ui.bundle.js',
  format: 'iife',
  target: 'es6',
  sourcemap: false,
  minify: !isWatch,
  logLevel: 'info',
};

async function buildUI() {
  // First build the UI JS bundle
  await esbuild.build(uiBuildOptions);

  // Read the generated JS bundle
  const uiJs = fs.readFileSync(path.join(__dirname, 'dist', 'ui.bundle.js'), 'utf-8');

  // Read the HTML template
  const uiHtml = fs.readFileSync(path.join(__dirname, 'src', 'ui.html'), 'utf-8');

  // Inject the JS bundle into the HTML
  const finalHtml = uiHtml.replace(
    '<!-- UI_SCRIPT_PLACEHOLDER -->',
    `<script>\n${uiJs}\n</script>`
  );

  // Write the final HTML file
  fs.writeFileSync(path.join(__dirname, 'dist', 'ui.html'), finalHtml, 'utf-8');

  // Clean up the intermediate JS bundle
  fs.unlinkSync(path.join(__dirname, 'dist', 'ui.bundle.js'));

  console.log('UI HTML built successfully with inlined JS.');
}

async function build() {
  // Ensure dist directory exists
  if (!fs.existsSync(path.join(__dirname, 'dist'))) {
    fs.mkdirSync(path.join(__dirname, 'dist'), { recursive: true });
  }

  if (isWatch) {
    // Watch mode: use esbuild's watch for main, rebuild UI on changes
    const mainCtx = await esbuild.context(mainBuildOptions);
    await mainCtx.watch();
    console.log('Watching main.ts for changes...');

    const uiCtx = await esbuild.context({
      ...uiBuildOptions,
      plugins: [
        {
          name: 'ui-html-inline',
          setup(build) {
            build.onEnd(async () => {
              try {
                await buildUI();
              } catch (err) {
                console.error('Error building UI HTML:', err);
              }
            });
          },
        },
      ],
    });
    await uiCtx.watch();
    console.log('Watching UI files for changes...');
  } else {
    // One-shot build
    await esbuild.build(mainBuildOptions);
    console.log('Main bundle built successfully.');

    await buildUI();
  }
}

build().catch((err) => {
  console.error('Build failed:', err);
  process.exit(1);
});
