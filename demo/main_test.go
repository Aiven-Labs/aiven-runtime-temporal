package main

import (
	"go.temporal.io/sdk/testsuite"
	"testing"
)

func TestGreetingRecoversFromFirstAttemptFailure(t *testing.T) {
	var suite testsuite.WorkflowTestSuite
	env := suite.NewTestWorkflowEnvironment()
	env.RegisterActivity(Greet)
	env.ExecuteWorkflow(GreetingWorkflow, "Aiven")
	if !env.IsWorkflowCompleted() {
		t.Fatal("workflow did not complete")
	}
	if err := env.GetWorkflowError(); err != nil {
		t.Fatal(err)
	}
	var result string
	if err := env.GetWorkflowResult(&result); err != nil {
		t.Fatal(err)
	}
	want := "Hello, Aiven! Temporal recovered from a failed activity on Aiven Runtime."
	if result != want {
		t.Fatalf("got %q, want %q", result, want)
	}
}
