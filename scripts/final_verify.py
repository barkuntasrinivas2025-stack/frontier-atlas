from pathlib import Path
import ast
required=['README.md','architecture.pdf','Dockerfile','docker-compose.yml','requirements.txt','.env.example','src','tests','scripts']
for x in required: assert Path(x).exists(), x
for p in Path('src').rglob('*.py'): ast.parse(p.read_text(encoding='utf-8'))
print('final verification: OK')
