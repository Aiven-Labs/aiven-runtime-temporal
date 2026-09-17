package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"time"

	"go.temporal.io/api/serviceerror"
	"go.temporal.io/api/workflowservice/v1"
	"go.temporal.io/sdk/activity"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/worker"
	"go.temporal.io/sdk/workflow"
	"google.golang.org/protobuf/types/known/durationpb"
)

const taskQueue = "aiven-demo"

func GreetingWorkflow(ctx workflow.Context, name string) (string, error) {
	ctx = workflow.WithActivityOptions(ctx, workflow.ActivityOptions{
		StartToCloseTimeout: 10 * time.Second,
		RetryPolicy:         &temporal.RetryPolicy{InitialInterval: 2 * time.Second, MaximumAttempts: 3},
	})
	var greeting string
	err := workflow.ExecuteActivity(ctx, Greet, name).Get(ctx, &greeting)
	return greeting, err
}

func Greet(ctx context.Context, name string) (string, error) {
	if activity.GetInfo(ctx).Attempt == 1 {
		return "", fmt.Errorf("intentional demo failure: Temporal will retry this activity")
	}
	return fmt.Sprintf("Hello, %s! Temporal recovered from a failed activity on Aiven Runtime.", name), nil
}

func main() {
	c, err := client.Dial(client.Options{HostPort: "127.0.0.1:7233", Namespace: "default"})
	if err != nil {
		log.Fatal(err)
	}
	defer c.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	_, err = c.WorkflowService().RegisterNamespace(ctx, &workflowservice.RegisterNamespaceRequest{
		Namespace: "default", WorkflowExecutionRetentionPeriod: durationpb.New(24 * time.Hour),
	})
	cancel()
	var exists *serviceerror.NamespaceAlreadyExists
	if err != nil && !errors.As(err, &exists) {
		log.Fatal(err)
	}
	w := worker.New(c, taskQueue, worker.Options{})
	w.RegisterWorkflow(GreetingWorkflow)
	w.RegisterActivity(Greet)
	if err := w.Start(); err != nil {
		log.Fatal(err)
	}
	defer w.Stop()
	// Namespace propagation can briefly lag registration.
	var run client.WorkflowRun
	for attempt := 0; attempt < 30; attempt++ {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		run, err = c.ExecuteWorkflow(ctx, client.StartWorkflowOptions{
			ID: "aiven-starter-demo", TaskQueue: taskQueue,
			WorkflowExecutionTimeout: 2 * time.Minute,
		}, GreetingWorkflow, "Aiven")
		cancel()
		if err == nil {
			break
		}
		var missing *serviceerror.NamespaceNotFound
		if !errors.As(err, &missing) {
			log.Fatal(err)
		}
		time.Sleep(time.Second)
	}
	if err != nil {
		log.Fatal(err)
	}
	log.Printf("Demo workflow started: %s / %s", run.GetID(), run.GetRunID())
	<-worker.InterruptCh()
}
