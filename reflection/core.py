class Reflection:
    def __init__(self, llm):
        self.llm = llm

    @staticmethod
    def _concat_and_format_texts(data):
        concatenatedTexts = []
        for entry in data:
            role = entry.get('role', '')
            all_texts = ' '.join(part['text'] for part in entry['parts'])
            concatenatedTexts.append(f"{role}: {all_texts} \n")
        return ''.join(concatenatedTexts)


    def __call__(self, chatHistory, lastItemsConsidereds=100):

        if len(chatHistory) >= lastItemsConsidereds:
            chatHistory = chatHistory[len(chatHistory) - lastItemsConsidereds:]

        historyString = self._concat_and_format_texts(chatHistory)

        higherLevelSummariesPrompt = """Given a chat history and the latest user question which might reference context in the chat history, formulate a standalone question in Vietnamese which can be understood without the chat history. Do NOT answer the question, just reformulate it if needed and otherwise return it as is. {historyString}
        """.format(historyString=historyString)
        # higherLevelSummariesPrompt = """Given a chat history and the latest user question which might reference context in the chat history, formulate a standalone question in Vietnamese that is clear and fully understandable without requiring the chat history. Focus on maintaining the intent and meaning of the user's latest question. Automatically discard irrelevant or outdated parts of the chat history to prioritize the most recent and relevant context. Do NOT answer the question; just reformulate it or return it as is. {historyString}
        #         """.format(historyString=historyString)

        print(higherLevelSummariesPrompt)

        # completion = self.llm.chat.completions.create(
        #     model="gpt-4o",
        #     messages=[
        #         {
        #             "role": "user",
        #             "content": higherLevelSummariesPrompt
        #         }
        #     ]
        # )
        completion= self.llm.generate_content(higherLevelSummariesPrompt)

        return completion

