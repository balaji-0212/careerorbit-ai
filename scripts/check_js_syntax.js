const fs = require('fs');
const child_process = require('child_process');

const html = fs.readFileSync('careerorbit/web/static/index.html', 'utf8');
const scriptMatches = [...html.matchAll(/<script[\s\S]*?>([\s\S]*?)<\/script>/gi)];
console.log('Script blocks found:', scriptMatches.length);
scriptMatches.forEach((m, idx) => {
    const code = m[1];
    const filename = `temp_script_${idx}.js`;
    fs.writeFileSync(filename, code);
    try {
        child_process.execSync(`node --check ${filename}`, { stdio: 'pipe' });
        console.log(`Script ${idx} syntax OK`);
    } catch (e) {
        console.error(`Script ${idx} syntax ERROR:`, e.stderr ? e.stderr.toString() : e.message);
    }
    try { fs.unlinkSync(filename); } catch (_) {}
});
