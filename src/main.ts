import core from '@actions/core';
import github from '@actions/github';


// https://docs.github.com/en/actions/creating-actions/creating-a-javascript-action

try {
    // `who-to-greet` input defined in action metadata file
    const nameToGreet: string = core.getInput('who-to-greet');
    console.log(`Hello ${nameToGreet}!`);
    const time: string = (new Date()).toTimeString();
    core.setOutput("time", time);
    // Get the JSON webhook payload for the event that triggered the workflow
    const payload = JSON.stringify(github.context.payload, undefined, 2)
    console.log(`The event payload: ${payload}`);
} catch (error) {
    core.setFailed(error.message);
}
