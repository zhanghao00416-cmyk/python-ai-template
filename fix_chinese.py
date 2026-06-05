import re

with open("tests/test_19_eval.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace the garbled Chinese test line with correct UTF-8 content
old_line = 'score = response_relevance("ʲô��RAG", "RAG��иїизи¡¿ç©¶å¼ºç¬¹æˆ¯æœ¯ç»¿è¯´")'
new_line = 'score = response_relevance("什么是RAG", "RAG是一种检索增强生成技术")'

if old_line in content:
    content = content.replace(old_line, new_line)
    print("Replaced garbled line")
else:
    # Fallback: try to find any response_relevance in test_chinese and replace
    pattern = r'(def test_chinese\(self\):\s+score = response_relevance\(").*?("\),\s*").*?("\))'
    def repl(m):
        return m.group(1) + '什么是RAG" , "RAG是一种检索增强生成技术"'
    content = re.sub(pattern, repl, content, flags=re.DOTALL)
    print("Used regex replacement")

with open("tests/test_19_eval.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Done")
