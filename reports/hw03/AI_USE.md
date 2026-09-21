AI Usage and Independent Verification
1. What did you use an AI assistant for, and what did you do yourself?

I used Claude Code as a tutor while working on both parts of the assignment. It helped me understand new concepts before I implemented them, including:

How signed session cookies work.

Why a server-side revocation store is needed for logout and idle-timeout enforcement.

How embeddings and cosine similarity work, including working through a numerical example.

How the three chunking techniques differ.

I wrote the code myself, including:

auth.py

The Bootstrap templates

build_corpus.py

rag_chunking_comparison.py

summarize_chunking_comparison.py

I used Claude Code when I was unsure how to get started, became stuck on an error, or needed an explanation of a concept. I then ran and tested the code myself.

I also independently tested the complete login, logout, and idle-timeout flow in the browser and with curl. I verified that logged-out and expired session cookies could not be reused.

For Part 2, I ran the corpus download and RAG chunking pipeline on my own computer using real source documents and an actual embedding model. I also wrote the five domain questions and expected answers myself before running the retrieval code, as required by the assignment.

2. One AI-produced output that was wrong or unsuitable, or one thing you independently verified

The initial corpus setup used four source documents, one for each sport in my domain schema. Based on their estimated sizes, the corpus appeared to be large enough to meet the assignment's 200 KB requirement. However, this estimate turned out to be incorrect.

3. How did you detect the problem or verify the result?

I discovered the problem by running build_corpus.py. The script downloaded the source documents, extracted their text, calculated the total corpus size, and checked whether it met the 200 KB requirement.

The output showed:

Total corpus size: 190,657 bytes (186.2 KB)
Meets 200KB requirement: False


This showed that the corpus was actually about 9.3 KB short of the requirement.

I would not have caught the issue by only looking at the document list or estimating the document sizes. Running the automated size check provided an objective verification of the actual corpus size.

4. What did you change, and why does it work now?

I added two more real, public, domain-relevant documents:

The fuller AYSO National Rules & Regulations document.

A Douglas County Parks & Recreation multi-sport policy document.

I then ran the same script again. The output confirmed that the corpus now met the requirement:

Total corpus size: 232,807 bytes (227.4 KB)
Meets 200KB requirement: True


The fix works because I verified the result by running the automated size check again instead of assuming that adding more documents would be sufficient.

Additional Data-Quality Issue Discovered During Verification

A similar verification process revealed a data-quality issue in Part 2.

When I ran find_semantic_miss.py on the actual retrieval results, I found that Semantic chunking retrieved the wrong source document for one question, even though its cosine similarity was relatively high at 0.7193.

The retrieval returned an older 2009–2010 AYSO rules booklet instead of the expected 2018 AYSO National Rules document. Both documents discussed team sizes by age division, but they provided different numbers for the same age group.

I did not expect this issue when building the corpus. I found it only because I checked the retrieval results programmatically against the expected source file.

This demonstrates why I independently verified the outputs of the RAG pipeline rather than relying only on similarity scores. A relatively high cosine similarity does not necessarily mean that the retrieved document is the correct or most authoritative source.