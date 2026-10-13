# Builds a single self-contained index.html from src.html by embedding img/*.jpg as data URIs
import base64, re, os
s = open('src.html').read()
def emb(m):
    p = m.group(0)
    return 'data:image/jpeg;base64,' + base64.b64encode(open(p,'rb').read()).decode()
s = re.sub(r'img/[a-z]+\.jpg', emb, s)
open('index.html','w').write(s)
print('index.html', os.path.getsize('index.html')//1024, 'KB')
