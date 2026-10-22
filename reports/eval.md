# Evaluation on the demo video

Demo: `demo/rooftop-bees.mp4`, 90 s, 7 speech chunks, 8 keyframes. Models: chat `ministral-14b-latest`, vision `ministral-14b-latest`, embeddings `mistral-embed`, Whisper `small` (local, CPU). Ingestion took 42 s.

19 questions: 8 answered only by the narration, 8 only by what is on screen, 3 that need both. An answer is correct when it contains the expected facts; a citation is right when it points inside the slide where the fact appears.

## Accuracy by question type

| Mode | Spoken only (8) | Shown only (8) | Both (3) | **All (19)** | Cited the right moment | LLM calls / question | Median latency |
|---|---|---|---|---|---|---|---|
| simple | 100% | 0% | 0% | **42%** | 63% | 2.0 | 0.8 s |
| multimodal | 100% | 100% | 100% | **100%** | 100% | 2.0 | 0.8 s |
| agentic | 100% | 100% | 100% | **100%** | 100% | 4.37 | 1.8 s |

## Every answer

| # | Type | Question | Mode | ✓ | Answer |
|---|---|---|---|---|---|
| 1 | speech | When was the first hive installed? | simple | ✅ | The first hive was installed on the roof of the city library in the **spring of 2019** [00:12–00:28]. |
| 1 | speech | When was the first hive installed? | multimodal | ✅ | The first hive was installed in the **spring of 2019** [00:12–00:24]. |
| 1 | speech | When was the first hive installed? | agentic | ✅ | The first hive was installed in the **spring of 2019** on the roof of the city library, as stated in the speech at [00:00–00:19] and [00:12–00:28]. |
| 2 | speech | On which building was the first hive installed? | simple | ✅ | The first hive was installed on the roof of the **city library** [00:12–00:28]. |
| 2 | speech | On which building was the first hive installed? | multimodal | ✅ | The first hive was installed on the roof of the **city library** [00:12–00:24]. |
| 2 | speech | On which building was the first hive installed? | agentic | ✅ | The first hive was installed on the **roof of the city library** in the spring of 2019, as stated in the speech at [00:00–00:19] and [00:12–00:28]. |
| 3 | speech | How many eggs can the queen lay per day? | simple | ✅ | According to the video, the queen can lay **up to 2000 eggs a day** at the height of the season, as stated at **[00:25–00:43]**. |
| 3 | speech | How many eggs can the queen lay per day? | multimodal | ✅ | According to the evidence, the queen can lay **up to 2,000 eggs a day** at the height of the season, as stated in the speech at **[00:25–00:43]**. |
| 3 | speech | How many eggs can the queen lay per day? | agentic | ✅ | According to the video, the queen can lay **up to 2000 eggs per day** at the height of the season, as stated in the speech at **[00:25–00:43]**. |
| 4 | speech | What should you do if you get stung? | simple | ✅ | If you get stung, you should scrape the sting out with a fingernail, as pinching it pushes more venom in [00:38–00:56]. |
| 4 | speech | What should you do if you get stung? | multimodal | ✅ | If you get stung, you should **scrape the sting out with a fingernail**—never pinch it, as that pushes more venom in, according to the instructions given at **[00:52–00:56]**. |
| 4 | speech | What should you do if you get stung? | agentic | ✅ | If you get stung, you should **scrape the sting out with a fingernail** and **never pinch it**, as pinching pushes more venom in, according to the advice given at **[00:38–00:56]**. |
| 5 | speech | What does the association lend beginners for free? | simple | ✅ | According to the video, the association lends beginners a **smoker for free** during their first year [00:53–01:13]. |
| 5 | speech | What does the association lend beginners for free? | multimodal | ✅ | According to the evidence, the association lends beginners a **smoker for free** during their first year, as stated at **[00:53–01:13]**. |
| 5 | speech | What does the association lend beginners for free? | agentic | ✅ | According to the video, the association lends beginners a **smoker for free** during their first year [00:53–01:13]. This is explicitly mentioned in the speech, though the screen does not list it as free. |
| 6 | speech | What breed is the queen? | simple | ✅ | The queen in the video is a **Buckfast** breed, as stated at **[01:06–01:22]**. |
| 6 | speech | What breed is the queen? | multimodal | ✅ | The queen is a **Buckfast** breed, as explicitly stated in the evidence at **[00:53–01:13]**. |
| 6 | speech | What breed is the queen? | agentic | ✅ | The queen is a **Buckfast breed**, as stated explicitly in the speech at **[00:53–01:13]**. |
| 7 | speech | How much honey was collected last year? | simple | ✅ | According to the video, **42 kg of honey** was collected last year, as stated at **[01:16–01:22]**. |
| 7 | speech | How much honey was collected last year? | multimodal | ✅ | According to the evidence, **42 kg of honey** was collected last year, as stated at **[1:12–1:29]**. |
| 7 | speech | How much honey was collected last year? | agentic | ✅ | The amount of honey collected last year was **42 kg**, as stated in the speech at **[01:06–01:22]** and **[01:16–01:29]**. This is the only explicit mention of honey collection in the video. |
| 8 | speech | When does the next beginner session start? | simple | ✅ | The next beginner session starts on **October 3rd**, as explicitly stated at **[01:26–01:29]**. |
| 8 | speech | When does the next beginner session start? | multimodal | ✅ | The next beginner session starts on **the 3rd of October**, as mentioned in the speech at **[01:16–01:29]**. |
| 8 | speech | When does the next beginner session start? | agentic | ✅ | The next beginner session starts on **the 3rd of October**, as stated in the speech at [01:16–01:29]. |
| 9 | screen | How many hives are there on the roof? | simple | ❌ | I could not find the exact number of hives on the roof in the provided evidence. The video only mentions the first hive installed in 2019 and that the apiary has "grown," but does not specify how many hives there are currently. |
| 9 | screen | How many hives are there on the roof? | multimodal | ✅ | According to the evidence, there are **6 hives** on the roof, as stated on the slide titled "Our apiary" at **[00:12–00:24]**. |
| 9 | screen | How many hives are there on the roof? | agentic | ✅ | There are **6 hives** on the roof, as shown on the slide at **[00:12–00:24]**. |
| 10 | screen | How high is the roof? | simple | ❌ | I could not find information about the height of the roof in the video. |
| 10 | screen | How high is the roof? | multimodal | ✅ | According to the evidence, the roof height is **[00:12–00:24] 24 meters**. |
| 10 | screen | How high is the roof? | agentic | ✅ | The roof height is **24 meters**, as shown on the slide at **[00:12–00:24]**. |
| 11 | screen | In which month does the colony peak, and how many bees does it have then? | simple | ❌ | The video does not specify the exact month when the colony peaks, nor does it provide the number of bees at that time. The chart mentioned at [00:25–00:43] shows population trends but is not visible or detailed in the provided evidence. |
| 11 | screen | In which month does the colony peak, and how many bees does it have then? | multimodal | ✅ | According to the evidence, the colony peaks in **[00:24–00:38]** **June**, with a population of **60,000 bees**. This is shown in the bar chart where June is highlighted in orange and labeled with the exact number. |
| 11 | screen | In which month does the colony peak, and how many bees does it have then? | agentic | ✅ | The colony peaks in **June** with **60,000 bees**, as shown by the highlighted bar in the chart at [00:24–00:38]. |
| 12 | screen | Below what temperature should the hive never be opened? | simple | ❌ | I could not find the specific temperature below which the hive should never be opened in the provided evidence. |
| 12 | screen | Below what temperature should the hive never be opened? | multimodal | ✅ | According to the video, the hive should never be opened below **[00:38–00:52]** **15 °C**. |
| 12 | screen | Below what temperature should the hive never be opened? | agentic | ✅ | The hive should never be opened below **15 °C** [00:38]. This rule is explicitly stated in the safety guidelines shown on screen. |
| 13 | screen | How much does the bee suit cost? | simple | ❌ | I could not find the cost of the bee suit in the provided evidence. |
| 13 | screen | How much does the bee suit cost? | multimodal | ✅ | The bee suit costs **120 €**, as shown in the "Beginner kit" list at **[00:52–01:03]**. |
| 13 | screen | How much does the bee suit cost? | agentic | ✅ | The bee suit costs **120 €**, as shown on the "Beginner kit" list at **[00:52–01:03]**. |
| 14 | screen | What colour is the mark on the queen? | simple | ❌ | I could not find any information about the color of a mark on the queen in the provided evidence. |
| 14 | screen | What colour is the mark on the queen? | multimodal | ✅ | The mark on the queen is **blue**, as shown in the slide titled "Our queen" at **[01:03–01:12]**, where the bee illustration has a blue dot on its thorax. |
| 14 | screen | What colour is the mark on the queen? | agentic | ✅ | The mark on the queen is a **blue dot**, as shown in the illustration on the slide titled "Our queen" at **[01:03–01:12]**. |
| 15 | screen | What is the price of a jar of honey? | simple | ❌ | I could not find the price of a jar of honey in the video. |
| 15 | screen | What is the price of a jar of honey? | multimodal | ✅ | According to the evidence, the price of a jar of honey is **9 € for 250 grams** [01:12–01:21]. |
| 15 | screen | What is the price of a jar of honey? | agentic | ✅ | I could not find the price of a **jar of honey** in the speech transcript, but the screen shows the price as **9 € for 250 g** [1:12–1:21]. |
| 16 | screen | On which day are the workshops held? | simple | ❌ | The video does not specify the day of the week for the workshops, only that the **next beginner session starts on the 3rd of October** [01:16–01:29]. |
| 16 | screen | On which day are the workshops held? | multimodal | ✅ | The workshops are held **every Saturday** at 10:00, as stated in the slide shown at **[1:21–1:30]**. |
| 16 | screen | On which day are the workshops held? | agentic | ✅ | The workshops are held **every Saturday at 10:00**, as shown on the final slide of the presentation **[1:21–1:30]**. |
| 17 | both | What is the total price of the four items in the beginner kit? | simple | ❌ | I could not find the total price of the four items in the beginner kit in the provided evidence. Only the mention of the kit and a note about the smoker being free during the first year were included. |
| 17 | both | What is the total price of the four items in the beginner kit? | multimodal | ✅ | The total price of the four items in the beginner kit is **185 €**, calculated by adding the prices: **120 €** (Bee suit) + **35 €** (Smoker) + **12 €** (Hive tool) + **18 €** (Gloves) as shown at **[00:52–01:03]**. |
| 17 | both | What is the total price of the four items in the beginner kit? | agentic | ✅ | The total price of the four items in the beginner kit is **185 €**, calculated as follows: - Bee suit: **120 €** [00:52–01:03] - Smoker: **35 €** [00:52–01:03] - Hive tool: **12 €** [00:52–01:03] - Gloves: **18 €** [00:52–01:03] **Total = 120 + 35 + 12 + 18 = 185 €**. |
| 18 | both | Which breed is the queen, and in which year was she marked? | simple | ❌ | The queen is a **Buckfast breed** [00:53–01:13], but the video does **not** mention the year she was marked. |
| 18 | both | Which breed is the queen, and in which year was she marked? | multimodal | ✅ | The queen is a **Buckfast breed** [00:53–01:13], and she was marked in **2024** [01:03–01:12]. |
| 18 | both | Which breed is the queen, and in which year was she marked? | agentic | ✅ | The queen is a **Buckfast breed**, as stated in the speech at **[00:53–01:13]**. She was marked in the year **2024**, as shown on the slide at **[01:03–01:12]**. |
| 19 | both | In which month is the honey harvested, and how much does a jar cost? | simple | ❌ | The honey is harvested in **late August** [01:06–01:22], but the video does **not provide** any information about the cost of a jar of honey. |
| 19 | both | In which month is the honey harvested, and how much does a jar cost? | multimodal | ✅ | According to the video, honey is harvested in **late August** [01:06–01:22], and each jar costs **9 € for 250 g** [01:12–01:21]. |
| 19 | both | In which month is the honey harvested, and how much does a jar cost? | agentic | ✅ | The honey is harvested in **late August** [01:06–01:22]. A jar of honey costs **9 € for 250 grams** [01:12–01:21]. |
