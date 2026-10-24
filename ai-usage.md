# AI Usage

## Tools used:
- Cursor IDE (Grok 4.6) -- for code implementation
- Claude (Sonnet 5.5) -- for refining prompts and one-off questions (syntax, domain, etc.)

## Which parts AI helped with:
### Implementation:
- My primary use of AI within this project was to write the actual code implementation. I scoped out the entire design (entities, data models, routes, functions, etc.), and broke it into small pieces that I could prompt Cursor with. My philosophy involves leaving as little ambiguity as possible. I use my spec to outline exactly what I want, how I want it, conventions to follow, etc. so the solution the AI writes is exactly in line with what I was looking for and it is verifiable.
### Testing:
- When using AI tools to write code, testing is of utmost importance. When using AI tools to write tests, its important to be aware of confimation bias, as the tests could be fitted to handle exactly what the code is able to do, rather than exposing gaps or bugs, which is why I try to come up with a lot of the tests. I quickly write out tests around boundaries, edge cases, and failure paths. Here's some examples: 
    - Balance 10000, purchase 10000 --> APPROVED, balance 0
    - Balance 10000, purchase 10001 --> DECLINED, balance 10000.
    - Declined purchases are still recorded as a Transaction, but with status DECLINED
    - create_account("") throws a ServiceError
-  during
### Prompting
- I used Cursor as a tool to help improve my prompting, by having it organize my information and outline practices and conventions I want to maintain good code smell as I develop. I would work back and forth from my initial spec until I had a prompt that had the exact details and specification I needed. Note that I wasn't using it as a means to plan out solutions, rather I was supplying my specifications and implementation requirements, and using it to better convey my ideas and organize the information so the coding agent generates more reliable, safe code that follows strong conventions.
lauderomptsin order tothe tool
## Prompting workflow examples I used

### Testing
- As I described earlier, when testing, I would write out some tests from the spec, with results that I computed, and use AI to write those tests out (along with others), with instructions to not derive expected values from the code itself, to protect against confirmation bias.
 explicit
### Feeback
- At the start of the project during my designing phase, I wrote out my entities and data models, as well as a list of questions/assumptions I was making, and used AI as a tool to challenge my design to strengthen what I had planned out where I felt the AI had merit. For example, my initial schema for the HsaAccount and Transaction entities had the balance/amount represented as numeric type with 2 decimal places. When AI provided feedback, it informed me that sqlite represents this as a floating point value behind the scenes. I then pivoted to representing currency as cents to avoid floating point values altogether.
rrorspotential 
## AI unhelpful example
- Overall, I took a very careful and thorough approach when using AI during this project, which resulted in primarily effective generations, however one area in which AI was incomplete was within the markdown files themselves. When using it to assist with writing the setup instructions within the README, it failed to consider other operating systems besides windows, so I had to go back and append to the setup instructions. It also made up the required Python version to be 3.10, which I quickly flagged and updated to the accurate version. Additionally, within architecture.md, I had to make a lot of small changes to the content of the file as it was over-complicating descriptions and not conveying ideas effectively. Some sections, such as the design tradeoffs, I completely re-did on my own as I felt the AI could not be helpful with this aspect. I owned the design of this project, and the AI make assumptions about tradeoffs wouldn't be accurate nor truthful.

## Verifying final implementation
- To verify the final implementation, I utilized regression testing with all of the tests I had generated throughout the implementation. Re-testing the models, business logic, routes, and concurrency allowed me to ensure a consistent, functional state. To test the UI, I expiremented with my list of scenarios and edge cases to ensure that boundaries were correct, and rules were enforced properly.