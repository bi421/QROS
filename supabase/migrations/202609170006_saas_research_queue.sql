-- Durable background queue for research execution.
-- Queue messages contain identifiers only; raw datasets and credentials never enter the queue.

create extension if not exists pgmq;

select pgmq.create('qros-research-runs');
